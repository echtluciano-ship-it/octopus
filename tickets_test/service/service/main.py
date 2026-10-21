from __future__ import annotations

import secrets

from fastapi import FastAPI, Header, HTTPException, Query

from service.config import settings
from service.db import connection
from service.export_excel import generate
from service.ingest import MediaNotAvailable, ingest
from service.object_store import client as minio_client
from service.reconcile import reconciliation


app = FastAPI(title="OCTOPUS Tickets TEST", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": "TEST", "actions": "BLOCKED_SHADOW"}


@app.get("/ready")
def ready() -> dict:
    try:
        with connection() as conn:
            conn.execute("SELECT 1").fetchone()
        minio_client().head_bucket(Bucket=settings.minio_bucket)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Dependency unavailable: {exc}") from exc
    return {"status": "ready"}


@app.post("/webhooks/evolution")
def evolution_webhook(
    payload: dict,
    x_octopus_webhook_token: str | None = Header(default=None),
) -> dict:
    if not x_octopus_webhook_token or not secrets.compare_digest(
        x_octopus_webhook_token, settings.webhook_token
    ):
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    try:
        return ingest(payload)
    except MediaNotAvailable as exc:
        # The event/message was already committed. A non-2xx response asks Evolution
        # to retry media delivery without making the original message disappear.
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/audit/reconciliation")
def audit_reconciliation() -> dict:
    return reconciliation()


@app.get("/tickets")
def tickets(limit: int = Query(default=100, ge=1, le=1000)) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """SELECT d.document_id,d.status,d.original_filename,d.sha256,d.duplicate_of,
                      d.duplicate_reason,d.last_error,m.arrival_sequence,m.group_id,
                      m.sender_name,m.message_timestamp,m.provider_message_id,
                      x.document_type,x.ticket_date,x.amount_cents,x.identifier_type,
                      x.identifier_value,x.full_name,x.tax_id,x.origin_bank,
                      x.destination_account_key,x.observations
                 FROM ticket_documents d JOIN inbound_messages m USING(message_id)
                 LEFT JOIN LATERAL (
                   SELECT * FROM ticket_extractions e WHERE e.document_id=d.document_id
                   ORDER BY attempt DESC LIMIT 1
                 ) x ON true
                ORDER BY m.arrival_sequence,d.attachment_index LIMIT %s""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/exports/generate")
def generate_exports() -> dict:
    return generate()
