from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from jarvis.tickets.models import AttachmentInput, IngestResult, MessageInput, TicketStatus


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TicketInbox:
    """SQLite laboratory inbox. Production will use the same constraints in Postgres."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        with closing(self._connect()) as conn, conn:
            conn.executescript(schema)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def record_message(
        self,
        message: MessageInput,
        attachments: Iterable[AttachmentInput],
    ) -> IngestResult:
        attachments = tuple(attachments)
        with closing(self._connect()) as conn, conn:
            existing = conn.execute(
                "SELECT message_id FROM inbound_messages WHERE provider=? AND instance_id=? "
                "AND group_id=? AND provider_message_id=?",
                (message.provider, message.instance_id, message.group_id, message.provider_message_id),
            ).fetchone()
            now = utc_now()
            inserted = existing is None
            if existing:
                message_id = int(existing["message_id"])
            else:
                cursor = conn.execute(
                    "INSERT INTO inbound_messages(provider,instance_id,group_id,group_name,provider_message_id,"
                    "sender_id,sender_name,message_timestamp,received_at,expected_attachments,raw_payload_json,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        message.provider,
                        message.instance_id,
                        message.group_id,
                        message.group_name,
                        message.provider_message_id,
                        message.sender_id,
                        message.sender_name,
                        message.message_timestamp,
                        message.received_at,
                        message.expected_attachments,
                        message.raw_payload_json,
                        now,
                    ),
                )
                message_id = int(cursor.lastrowid)
            document_ids: list[int] = []
            duplicate_ids: list[int] = []
            for attachment in attachments:
                stored = conn.execute(
                    "SELECT document_id, duplicate_of FROM ticket_documents "
                    "WHERE message_id=? AND attachment_index=?",
                    (message_id, attachment.attachment_index),
                ).fetchone()
                if stored:
                    document_ids.append(int(stored["document_id"]))
                    if stored["duplicate_of"]:
                        duplicate_ids.append(int(stored["document_id"]))
                    continue
                duplicate = conn.execute(
                    "SELECT document_id FROM ticket_documents WHERE sha256=? AND size_bytes=? "
                    "ORDER BY document_id LIMIT 1",
                    (attachment.sha256, attachment.size_bytes),
                ).fetchone()
                status = TicketStatus.DUPLICATE_CONFIRMED if duplicate else TicketStatus.ORIGINAL_STORED
                reason = "identical SHA-256 and byte size" if duplicate else None
                doc_cursor = conn.execute(
                    "INSERT INTO ticket_documents(message_id,attachment_index,original_filename,mime_type,"
                    "size_bytes,sha256,visual_hash,object_uri,status,duplicate_of,duplicate_reason,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        message_id,
                        attachment.attachment_index,
                        attachment.original_filename,
                        attachment.mime_type,
                        attachment.size_bytes,
                        attachment.sha256,
                        attachment.visual_hash,
                        attachment.object_uri,
                        status.value,
                        duplicate["document_id"] if duplicate else None,
                        reason,
                        now,
                        now,
                    ),
                )
                document_id = int(doc_cursor.lastrowid)
                document_ids.append(document_id)
                if duplicate:
                    duplicate_ids.append(document_id)
                    conn.execute(
                        "INSERT INTO duplicate_evidence(document_id,candidate_document_id,evidence_type,"
                        "evidence_value,strength,decision,decided_by,created_at) VALUES (?,?,?,?,?,?,?,?)",
                        (
                            document_id,
                            duplicate["document_id"],
                            "sha256",
                            attachment.sha256,
                            "EXACT",
                            "CONFIRMED",
                            "deterministic-rule",
                            now,
                        ),
                    )
                conn.execute(
                    "INSERT INTO ticket_state_events(document_id,previous_status,new_status,actor,reason,"
                    "evidence_json,created_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        document_id,
                        None,
                        status.value,
                        "whatsapp-ingest",
                        reason or "original persisted before interpretation",
                        json.dumps({"sha256": attachment.sha256, "object_uri": attachment.object_uri}),
                        now,
                    ),
                )
            return IngestResult(
                message_id=message_id,
                arrival_sequence=message_id,
                inserted=inserted,
                document_ids=tuple(document_ids),
                exact_duplicate_ids=tuple(duplicate_ids),
            )

    def transition(
        self,
        document_id: int,
        new_status: TicketStatus,
        *,
        actor: str,
        reason: str,
        evidence: dict | None = None,
    ) -> None:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT status FROM ticket_documents WHERE document_id=?", (document_id,)
            ).fetchone()
            if not row:
                raise KeyError(f"Unknown ticket document {document_id}")
            previous = row["status"]
            now = utc_now()
            conn.execute(
                "UPDATE ticket_documents SET status=?, updated_at=? WHERE document_id=?",
                (new_status.value, now, document_id),
            )
            conn.execute(
                "INSERT INTO ticket_state_events(document_id,previous_status,new_status,actor,reason,"
                "evidence_json,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    document_id,
                    previous,
                    new_status.value,
                    actor,
                    reason,
                    json.dumps(evidence or {}, ensure_ascii=True, sort_keys=True),
                    now,
                ),
            )

    def documents_in_arrival_order(self) -> list[sqlite3.Row]:
        with closing(self._connect()) as conn:
            return conn.execute(
                "SELECT d.*, m.message_timestamp, m.received_at, m.group_name, m.provider_message_id "
                "FROM ticket_documents d JOIN inbound_messages m USING(message_id) "
                "ORDER BY m.message_id, d.attachment_index"
            ).fetchall()

    def reconciliation(self) -> dict[str, int | bool]:
        groups = {
            "processed": {
                TicketStatus.READY_FOR_SHEET.value,
                TicketStatus.SHEET_GENERATED.value,
                TicketStatus.SHADOW_COMPARED.value,
            },
            "duplicates": {TicketStatus.DUPLICATE_CONFIRMED.value},
            "review": {
                TicketStatus.REVIEW.value,
                TicketStatus.WRONG_ACCOUNT_REVIEW.value,
                TicketStatus.CHECK_REVIEW.value,
            },
            "errors": {TicketStatus.ERROR_RETRYABLE.value, TicketStatus.ERROR_FINAL.value},
        }
        with closing(self._connect()) as conn:
            message_totals = conn.execute(
                "SELECT COUNT(*) messages, COALESCE(SUM(expected_attachments), 0) expected "
                "FROM inbound_messages"
            ).fetchone()
            rows = conn.execute(
                "SELECT status, COUNT(*) count FROM ticket_documents GROUP BY status"
            ).fetchall()
        counts = {row["status"]: int(row["count"]) for row in rows}
        total = sum(counts.values())
        expected = int(message_totals["expected"])
        result: dict[str, int | bool] = {
            "received_messages": int(message_totals["messages"]),
            "expected_documents": expected,
            "received_documents": total,
            "missing_documents": max(expected - total, 0),
        }
        classified = 0
        for label, statuses in groups.items():
            value = sum(counts.get(status, 0) for status in statuses)
            result[label] = value
            classified += value
        result["in_progress"] = total - classified
        result["balanced"] = total == classified + int(result["in_progress"])
        result["ingest_balanced"] = expected == total
        return result
