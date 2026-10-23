from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from typing import Any

import requests
from PIL import Image, ImageOps

from service.config import settings
from service.db import connection
from service.object_store import put_original
from service.workflow import record_duplicate_shadow_action


MEDIA_KEYS = ("imageMessage", "documentMessage", "videoMessage")
TICKET_EVENT_TYPES = frozenset({"messages.upsert"})


class MediaNotAvailable(RuntimeError):
    pass


def record_ingest_failure(payload: dict[str, Any], error: Exception) -> None:
    parts = _message_parts(payload)
    if (
        not parts["message_id"]
        or not parts["remote_jid"]
        or not _allowed_group(parts["remote_jid"])
    ):
        return
    with connection() as conn:
        message = conn.execute(
            """SELECT message_id FROM inbound_messages
               WHERE provider='evolution' AND instance_name=%s AND group_id=%s
                 AND provider_message_id=%s""",
            (parts["instance"], parts["remote_jid"], parts["message_id"]),
        ).fetchone()
        if message is None:
            return
        conn.execute(
            """INSERT INTO ingest_failures(message_id,attachment_index,last_error)
               VALUES (%s,0,%s)
               ON CONFLICT(message_id,attachment_index) DO UPDATE SET
                 status='ERROR_RETRYABLE',
                 attempts=ingest_failures.attempts+1,
                 last_error=EXCLUDED.last_error,
                 last_failed_at=now(),
                 resolved_at=NULL""",
            (message["message_id"], f"{type(error).__name__}: {error}"[:2000]),
        )
        conn.commit()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str)


def _without_binary(value: Any) -> Any:
    clean = copy.deepcopy(value)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for key in list(node):
                if key.lower() in {"base64", "jpegthumbnail"}:
                    node[key] = "[BINARY_REMOVED]"
                else:
                    visit(node[key])
        elif isinstance(node, list):
            for item in node:
                visit(item)

    visit(clean)
    return clean


def _timestamp(value: Any) -> datetime:
    if isinstance(value, dict):
        value = value.get("low") or value.get("seconds")
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc)


def _message_parts(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data") or {}
    key = data.get("key") or {}
    message = data.get("message") or {}
    remote_jid = str(key.get("remoteJid") or data.get("remoteJid") or "")
    provider_message_id = str(key.get("id") or data.get("id") or "")
    media_node: dict[str, Any] | None = None
    media_key: str | None = None
    wrapped = message.get("documentWithCaptionMessage")
    if isinstance(wrapped, dict):
        wrapped_message = wrapped.get("message") or {}
        if isinstance(wrapped_message.get("documentMessage"), dict):
            media_key = "documentMessage"
            media_node = wrapped_message["documentMessage"]
    for candidate in MEDIA_KEYS:
        if media_node is not None:
            break
        value = message.get(candidate)
        if isinstance(value, dict):
            media_key = candidate
            media_node = value
            break
    return {
        "instance": str(payload.get("instance") or "unknown"),
        "remote_jid": remote_jid,
        "group_name": settings.group_name(
            remote_jid,
            str(data.get("groupName") or data.get("chatName") or data.get("subject") or "") or None,
        ),
        "message_id": provider_message_id,
        "participant": str(key.get("participant") or data.get("participant") or ""),
        "sender_name": data.get("pushName"),
        "timestamp": _timestamp(data.get("messageTimestamp")),
        "message": message,
        "media_key": media_key,
        "media_node": media_node,
        "source": data.get("source") if isinstance(data.get("source"), dict) else {},
    }


def event_key(payload: dict[str, Any], raw_sha256: str) -> str:
    event_type = str(payload.get("event") or "unknown")
    parts = _message_parts(payload)
    if event_type == "messages.upsert" and parts["message_id"]:
        stable = "|".join(
            (event_type, parts["instance"], parts["remote_jid"], parts["message_id"])
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()
    return raw_sha256


def _media_content(parts: dict[str, Any]) -> tuple[bytes, str, str] | None:
    media = parts["media_node"]
    if media is None:
        return None
    message = parts["message"]
    encoded = message.get("base64") or media.get("base64")
    if encoded:
        if "," in encoded and encoded.lower().startswith("data:"):
            encoded = encoded.split(",", 1)[1]
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise MediaNotAvailable(f"invalid webhook base64: {exc}") from exc
    else:
        media_url = message.get("mediaUrl") or media.get("mediaUrl")
        if not media_url:
            raise MediaNotAvailable("media metadata exists but no base64 or downloadable URL was supplied")
        try:
            response = requests.get(media_url, timeout=45)
            response.raise_for_status()
            content = response.content
        except requests.RequestException as exc:
            raise MediaNotAvailable(f"media download failed: {exc}") from exc
    if not content:
        raise MediaNotAvailable("media download returned zero bytes")
    mime_type = str(media.get("mimetype") or "application/octet-stream")
    extension = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "application/pdf": ".pdf",
    }.get(mime_type, ".bin")
    filename = str(media.get("fileName") or f"{parts['message_id']}{extension}")
    return content, mime_type, filename


def _visual_hash(content: bytes, mime_type: str) -> str | None:
    if not mime_type.startswith("image/"):
        return None
    try:
        with Image.open(io.BytesIO(content)) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
            header = f"{image.width}x{image.height}|RGBA|".encode("ascii")
            return hashlib.sha256(header + image.tobytes()).hexdigest()
    except Exception:
        return None


def _allowed_group(group_id: str) -> bool:
    return group_id.endswith("@g.us") and (
        settings.accept_all_test_groups or group_id in settings.allowed_group_ids
    )


def ingest(payload: dict[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("event") or "unknown")
    if event_type not in TICKET_EVENT_TYPES:
        return {
            "event_id": None,
            "event_inserted": False,
            "ticket": False,
            "reason": f"event type {event_type!r} is outside the durable ticket inbox",
        }
    parts = _message_parts(payload)
    if not parts["message_id"]:
        return {
            "event_id": None,
            "event_inserted": False,
            "ticket": False,
            "reason": "message has no provider identifier",
        }
    if not _allowed_group(parts["remote_jid"]):
        return {
            "event_id": None,
            "event_inserted": False,
            "ticket": False,
            "reason": "message is outside configured TEST groups",
        }

    clean_payload = _without_binary(payload)
    raw = _canonical_json(clean_payload)
    raw_sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    key = event_key(payload, raw_sha)
    source = parts["source"]
    source_system = source.get("system") or "whatsapp_evolution"
    source_document_id = source.get("document_id") or parts["message_id"]

    with connection() as conn:
        event_row = conn.execute(
            """
            INSERT INTO ingress_events(event_key,event_type,instance_name,raw_payload,raw_sha256)
            VALUES (%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT(event_key) DO NOTHING
            RETURNING event_id
            """,
            (key, event_type, parts["instance"], raw, raw_sha),
        ).fetchone()
        if event_row:
            event_id = event_row["event_id"]
            inserted_event = True
        else:
            event_id = conn.execute(
                "SELECT event_id FROM ingress_events WHERE event_key=%s", (key,)
            ).fetchone()["event_id"]
            inserted_event = False

        if event_type != "messages.upsert" or not parts["message_id"]:
            conn.commit()
            return {"event_id": event_id, "event_inserted": inserted_event, "ticket": False}

        expected = 1 if parts["media_node"] is not None else 0
        message_row = conn.execute(
            """
            INSERT INTO inbound_messages(
                event_id,instance_name,group_id,group_name,provider_message_id,
                sender_id,sender_name,message_timestamp,expected_attachments
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(provider,instance_name,group_id,provider_message_id) DO NOTHING
            RETURNING message_id,arrival_sequence
            """,
            (
                event_id,
                parts["instance"],
                parts["remote_jid"],
                parts["group_name"],
                parts["message_id"],
                parts["participant"],
                parts["sender_name"],
                parts["timestamp"],
                expected,
            ),
        ).fetchone()
        if message_row is None:
            message_row = conn.execute(
                """SELECT message_id,arrival_sequence FROM inbound_messages
                WHERE provider='evolution' AND instance_name=%s AND group_id=%s AND provider_message_id=%s""",
                (parts["instance"], parts["remote_jid"], parts["message_id"]),
            ).fetchone()
        conn.commit()

    if expected == 0:
        return {
            "event_id": event_id,
            "message_id": message_row["message_id"],
            "ticket": False,
            "reason": "group message has no supported attachment",
        }

    media = _media_content(parts)
    if media is None:
        raise MediaNotAvailable("expected media was not available")
    content, mime_type, filename = media
    sha256 = hashlib.sha256(content).hexdigest()
    visual_hash = _visual_hash(content, mime_type)
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)[:120]
    object_key = (
        f"originals/{parts['instance']}/{parts['remote_jid']}/"
        f"{parts['message_id']}/0-{sha256[:12]}-{safe_name}"
    )
    put_original(object_key, content, mime_type)

    with connection() as conn:
        existing_document = conn.execute(
            "SELECT document_id,status,duplicate_of FROM ticket_documents "
            "WHERE message_id=%s AND attachment_index=0",
            (message_row["message_id"],),
        ).fetchone()
        if existing_document:
            conn.execute(
                """UPDATE ticket_documents
                      SET source_system=COALESCE(source_system,%s),
                          source_document_id=COALESCE(source_document_id,%s),
                          source_url=COALESCE(source_url,%s),
                          source_batch=COALESCE(source_batch,%s)
                    WHERE document_id=%s""",
                (
                    source_system,
                    source_document_id,
                    source.get("url"),
                    source.get("batch"),
                    existing_document["document_id"],
                ),
            )
            conn.commit()
            return {
                "event_id": event_id,
                "message_id": message_row["message_id"],
                "document_id": existing_document["document_id"],
                "ticket": True,
                "idempotent_replay": True,
            }

        duplicate = conn.execute(
            """SELECT document_id,sha256,visual_hash FROM ticket_documents
               WHERE sha256=%s OR visual_hash=%s
               ORDER BY document_id LIMIT 1""",
            (sha256, visual_hash),
        ).fetchone()
        status = "DUPLICATE_CONFIRMED" if duplicate else "ORIGINAL_STORED"
        reason = None
        if duplicate:
            reason = (
                "identical SHA-256"
                if duplicate["sha256"] == sha256
                else "pixel-identical image"
            )
        document = conn.execute(
            """
            INSERT INTO ticket_documents(
                message_id,attachment_index,original_filename,mime_type,size_bytes,
                sha256,visual_hash,object_key,status,duplicate_of,duplicate_reason,
                source_system,source_document_id,source_url
                ,source_batch
            ) VALUES (%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING document_id
            """,
            (
                message_row["message_id"],
                filename,
                mime_type,
                len(content),
                sha256,
                visual_hash,
                object_key,
                status,
                duplicate["document_id"] if duplicate else None,
                reason,
                source_system,
                source_document_id,
                source.get("url"),
                source.get("batch"),
            ),
        ).fetchone()
        document_id = document["document_id"]
        conn.execute(
            """UPDATE ingest_failures SET resolved_at=now(),status='RESOLVED'
               WHERE message_id=%s AND attachment_index=0 AND resolved_at IS NULL""",
            (message_row["message_id"],),
        )
        conn.execute(
            """INSERT INTO ticket_state_events(document_id,previous_status,new_status,actor,reason,evidence)
            VALUES (%s,NULL,%s,'evolution-ingest',%s,%s::jsonb)""",
            (
                document_id,
                status,
                reason or "original persisted before interpretation",
                _canonical_json({
                    "sha256": sha256,
                    "visual_hash": visual_hash,
                    "object_key": object_key,
                    "source": parts["source"],
                }),
            ),
        )
        if not duplicate:
            conn.execute("INSERT INTO processing_jobs(document_id) VALUES (%s)", (document_id,))
        conn.commit()
    if duplicate:
        record_duplicate_shadow_action(document_id, reason or "Copia documental exacta.")
    return {
        "event_id": event_id,
        "message_id": message_row["message_id"],
        "document_id": document_id,
        "ticket": True,
        "duplicate": bool(duplicate),
    }
