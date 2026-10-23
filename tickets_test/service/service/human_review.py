from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from service.config import settings
from service.db import connection
from service.extract import EXTRACTOR_VERSION
from service.export_excel import generate
from service.workflow import classify, queue_shadow_action, transition


EDITABLE_FIELDS = {
    "document_type",
    "ticket_date",
    "amount_cents",
    "identifier_type",
    "identifier_value",
    "full_name",
    "tax_id",
    "origin_bank",
    "destination_account_key",
}


def merge_review_fields(base: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    unknown = set(fields) - EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Unsupported human-review fields: {sorted(unknown)}")
    result = dict(base)
    result.update(fields)
    if isinstance(result.get("ticket_date"), str):
        result["ticket_date"] = date.fromisoformat(result["ticket_date"])
    account_key = result.get("destination_account_key")
    result["account_matches"] = [account_key] if account_key else []
    required = {
        "transfer": (
            "ticket_date",
            "amount_cents",
            "identifier_value",
            "full_name",
            "tax_id",
            "origin_bank",
        ),
        "deposit": ("ticket_date", "amount_cents", "identifier_value", "origin_bank"),
    }.get(result.get("document_type"), ())
    result["missing_fields"] = [field for field in required if result.get(field) in (None, "")]
    return result


def latest_review_for_sha(conn, sha256: str) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT correction_id,correction_key,fields,reason,evidence,reviewer
           FROM ticket_human_corrections
           WHERE sha256=%s ORDER BY created_at DESC,correction_id DESC LIMIT 1""",
        (sha256,),
    ).fetchone()
    return dict(row) if row else None


def _latest_extraction(conn, document_id: int) -> dict[str, Any]:
    row = conn.execute(
        """SELECT * FROM ticket_extractions
           WHERE document_id=%s ORDER BY attempt DESC LIMIT 1""",
        (document_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Document {document_id} has no extraction")
    result = dict(row)
    result.pop("extraction_id", None)
    result.pop("created_at", None)
    return result


def apply_batch(path: Path) -> dict[str, Any]:
    batch = json.loads(path.read_text(encoding="utf-8"))
    applied = 0
    skipped = 0
    documents: list[int] = []
    with connection() as conn:
        for item in batch["corrections"]:
            existing = conn.execute(
                "SELECT correction_id FROM ticket_human_corrections WHERE correction_key=%s",
                (item["correction_key"],),
            ).fetchone()
            if existing:
                skipped += 1
                continue
            correction = conn.execute(
                """INSERT INTO ticket_human_corrections(
                       correction_key,sha256,fields,reason,evidence,reviewer
                   ) VALUES (%s,%s,%s::jsonb,%s,%s::jsonb,%s)
                   RETURNING correction_id""",
                (
                    item["correction_key"],
                    item["sha256"],
                    json.dumps(item["fields"]),
                    item["reason"],
                    json.dumps(item.get("evidence", {})),
                    batch["reviewer"],
                ),
            ).fetchone()
            matched = conn.execute(
                "SELECT document_id FROM ticket_documents WHERE sha256=%s ORDER BY document_id",
                (item["sha256"],),
            ).fetchall()
            if not matched:
                raise ValueError(f"No document matches SHA-256 {item['sha256']}")
            for document_row in matched:
                document_id = document_row["document_id"]
                base = _latest_extraction(conn, document_id)
                reviewed = merge_review_fields(base, item["fields"])
                status, classification_reason = classify(reviewed, settings.account_config())
                next_attempt = int(base["attempt"]) + 1
                evidence = {
                    "human_correction_id": correction["correction_id"],
                    "correction_key": item["correction_key"],
                    "missing_fields": reviewed["missing_fields"],
                    "source_evidence": item.get("evidence", {}),
                }
                observation = (
                    classification_reason
                    if status == "READY_FOR_SHEET"
                    else f"{classification_reason} Revisión visual: {item['reason']}"
                )
                conn.execute(
                    """INSERT INTO ticket_extractions(
                         document_id,attempt,document_type,ticket_date,amount_cents,
                         identifier_type,identifier_value,full_name,tax_id,origin_bank,
                         destination_account_key,observations,ocr_text,confidence,evidence,
                         extractor_version
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)""",
                    (
                        document_id,
                        next_attempt,
                        reviewed.get("document_type"),
                        reviewed.get("ticket_date"),
                        reviewed.get("amount_cents"),
                        reviewed.get("identifier_type"),
                        reviewed.get("identifier_value"),
                        reviewed.get("full_name"),
                        reviewed.get("tax_id"),
                        reviewed.get("origin_bank"),
                        reviewed.get("destination_account_key"),
                        observation,
                        base["ocr_text"],
                        json.dumps({"mode": "human_visual_review", "human_validated": True}),
                        json.dumps(evidence),
                        f"{EXTRACTOR_VERSION}+human-review",
                    ),
                )
                transition(
                    conn,
                    document_id,
                    status,
                    actor="tickets-human-review",
                    reason=observation,
                    evidence=evidence,
                )
                queue_shadow_action(conn, document_id, status, observation)
                documents.append(document_id)
                applied += 1
        conn.commit()
    if documents:
        generate(document_id=documents)
    return {"applied": applied, "skipped": skipped, "documents": documents}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply auditable human review to ticket documents")
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    print(json.dumps(apply_batch(args.batch), indent=2))


if __name__ == "__main__":
    main()
