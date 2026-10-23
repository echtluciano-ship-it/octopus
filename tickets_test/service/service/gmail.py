from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from service.config import settings
from service.db import connection


GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
EMAIL_ACTION = "EMAIL_SEND"
APPROVED_TEST = "APPROVED_TEST_EMAIL"


def _resolved_attachment(path: str | Path) -> Path:
    root = settings.gmail_attachment_root.resolve()
    candidate = Path(path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Attachment outside configured root: {candidate}")
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def attachment_evidence(path: str | Path) -> dict[str, Any]:
    candidate = _resolved_attachment(path)
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(candidate),
        "name": candidate.name,
        "size": candidate.stat().st_size,
        "sha256": digest.hexdigest(),
    }


def queue_email(
    *,
    recipient: str,
    subject: str,
    body: str,
    attachments: list[str | Path],
    idempotency_key: str,
) -> int:
    recipient = recipient.strip().lower()
    if recipient not in settings.gmail_allowed_recipients:
        raise ValueError(f"Recipient is not allowlisted: {recipient}")
    payload = {
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "attachments": [attachment_evidence(path) for path in attachments],
    }
    with connection() as conn:
        inserted = conn.execute(
            """INSERT INTO action_outbox(
                 action_type,payload,approval_status,delivery_status,idempotency_key
               ) VALUES (%s,%s::jsonb,%s,'NOT_SENT',%s)
               ON CONFLICT(idempotency_key) DO NOTHING
               RETURNING action_id""",
            (EMAIL_ACTION, json.dumps(payload), APPROVED_TEST, idempotency_key),
        ).fetchone()
        if inserted:
            action_id = inserted["action_id"]
        else:
            existing = conn.execute(
                "SELECT action_id FROM action_outbox WHERE idempotency_key=%s",
                (idempotency_key,),
            ).fetchone()
            action_id = existing["action_id"]
        conn.commit()
    return int(action_id)


def build_message(payload: dict[str, Any], idempotency_key: str) -> EmailMessage:
    message = EmailMessage()
    message["To"] = payload["recipient"]
    message["Subject"] = payload["subject"]
    safe_key = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    message["Message-ID"] = f"<{safe_key}@tickets.octopus.local>"
    message.set_content(payload["body"])
    for item in payload["attachments"]:
        path = _resolved_attachment(item["path"])
        evidence = attachment_evidence(path)
        if evidence["sha256"] != item["sha256"] or evidence["size"] != item["size"]:
            raise ValueError(f"Attachment changed after queueing: {path.name}")
        mime, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (mime or "application/octet-stream").split("/", 1)
        message.add_attachment(
            path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name
        )
    return message


def gmail_service():
    import httplib2
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build

    token_path = settings.gmail_token_path
    if not token_path.is_file():
        raise RuntimeError("Gmail is not authorized; run the OAuth authorization step first.")
    credentials = Credentials.from_authorized_user_file(str(token_path), [GMAIL_SEND_SCOPE])
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    if not credentials.valid:
        raise RuntimeError("Gmail authorization is invalid or revoked.")
    ca_bundle = os.getenv("SSL_CERT_FILE", "/etc/ssl/certs/ca-certificates.crt")
    transport = httplib2.Http(ca_certs=ca_bundle)
    authorized_http = AuthorizedHttp(credentials, http=transport)
    return build("gmail", "v1", http=authorized_http, cache_discovery=False)


def send_action(action_id: int, *, service=None) -> dict[str, Any]:
    with connection() as conn:
        row = conn.execute(
            """SELECT action_id,payload,idempotency_key,delivery_status
               FROM action_outbox
               WHERE action_id=%s AND action_type=%s AND approval_status=%s
               FOR UPDATE""",
            (action_id, EMAIL_ACTION, APPROVED_TEST),
        ).fetchone()
        if row is None:
            raise KeyError(f"Approved email action not found: {action_id}")
        if row["delivery_status"] == "SENT":
            return {"action_id": action_id, "status": "SENT", "already_sent": True}
        if row["delivery_status"] == "SENDING":
            raise RuntimeError("Previous delivery is uncertain; manual audit required before retry.")
        if row["delivery_status"] == "DELIVERY_UNCERTAIN":
            raise RuntimeError("Delivery is uncertain; manual audit required before retry.")
        conn.execute(
            """UPDATE action_outbox
               SET delivery_status='SENDING',attempts=attempts+1,last_error=NULL
               WHERE action_id=%s""",
            (action_id,),
        )
        conn.commit()

    payload = row["payload"]
    message = build_message(payload, row["idempotency_key"])
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
    try:
        provider = service or gmail_service()
        response = provider.users().messages().send(userId="me", body={"raw": raw}).execute()
    except Exception as exc:
        status = "RETRYABLE_ERROR" if isinstance(exc, ssl.SSLCertVerificationError) else "DELIVERY_UNCERTAIN"
        with connection() as conn:
            conn.execute(
                """UPDATE action_outbox
                   SET delivery_status=%s,last_error=%s
                   WHERE action_id=%s""",
                (status, str(exc), action_id),
            )
            conn.commit()
        raise

    with connection() as conn:
        conn.execute(
            """UPDATE action_outbox
               SET delivery_status='SENT',provider_message_id=%s,delivered_at=now(),last_error=NULL
               WHERE action_id=%s""",
            (response.get("id"), action_id),
        )
        conn.commit()
    return {
        "action_id": action_id,
        "status": "SENT",
        "provider_message_id": response.get("id"),
        "recipient": payload["recipient"],
    }
