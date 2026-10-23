from __future__ import annotations

import json
import os
import socket
import time
import traceback

from service.config import settings
from service.db import connection
from service.export_excel import generate
from service.extract import EXTRACTOR_VERSION, ocr, parse
from service.human_review import latest_review_for_sha, merge_review_fields
from service.object_store import get_original
from service.workflow import classify, queue_shadow_action, transition


WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
MAX_ATTEMPTS = 5


def claim() -> dict | None:
    with connection() as conn:
        row = conn.execute(
            """
            WITH candidate AS (
              SELECT job_id FROM processing_jobs
              WHERE status IN ('PENDING','RETRY') AND available_at <= now()
              ORDER BY job_id FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE processing_jobs j
               SET status='PROCESSING',attempts=attempts+1,locked_at=now(),locked_by=%s,updated_at=now()
              FROM candidate c WHERE j.job_id=c.job_id
            RETURNING j.job_id,j.document_id,j.attempts
            """,
            (WORKER_ID,),
        ).fetchone()
        if row:
            transition(
                conn,
                row["document_id"],
                "PROCESSING",
                actor="tickets-worker",
                reason=f"Intento de procesamiento {row['attempts']}.",
                evidence={"job_id": row["job_id"], "worker": WORKER_ID},
            )
        conn.commit()
        return dict(row) if row else None


def process(job: dict) -> None:
    with connection() as conn:
        document = conn.execute(
            "SELECT object_key,mime_type,sha256 FROM ticket_documents WHERE document_id=%s",
            (job["document_id"],),
        ).fetchone()
    content = get_original(document["object_key"])
    supported = document["mime_type"].startswith("image/") or document["mime_type"] == "application/pdf"
    if supported:
        ocr_text = ocr(content, document["mime_type"])
        extracted = parse(ocr_text, settings.account_config())
        with connection() as conn:
            human_review = latest_review_for_sha(conn, document["sha256"])
        if human_review:
            extracted = merge_review_fields(extracted, human_review["fields"])
        status, reason = classify(extracted, settings.account_config())
    else:
        ocr_text = ""
        extracted = {
            "document_type": None,
            "ticket_date": None,
            "amount_cents": None,
            "identifier_type": None,
            "identifier_value": None,
            "full_name": None,
            "tax_id": None,
            "origin_bank": None,
            "destination_account_key": None,
            "account_matches": [],
            "missing_fields": [],
        }
        status = "REVIEW"
        reason = f"Formato no automatizado en TEST: {document['mime_type']}."
        human_review = None
    evidence = {
        "missing_fields": extracted.get("missing_fields", []),
        "account_matches": extracted.get("account_matches", []),
        "sender_identity_type": extracted.get("tax_id_type"),
    }
    if human_review:
        evidence["human_correction_id"] = human_review["correction_id"]
        evidence["correction_key"] = human_review["correction_key"]
    with connection() as conn:
        extraction_attempt = conn.execute(
            "SELECT COALESCE(MAX(attempt), 0) + 1 AS value FROM ticket_extractions WHERE document_id=%s",
            (job["document_id"],),
        ).fetchone()["value"]
        conn.execute(
            """INSERT INTO ticket_extractions(
                 document_id,attempt,document_type,ticket_date,amount_cents,
                 identifier_type,identifier_value,full_name,tax_id,origin_bank,
                 destination_account_key,observations,ocr_text,confidence,evidence,extractor_version
               ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)""",
            (
                job["document_id"], extraction_attempt, extracted.get("document_type"),
                extracted.get("ticket_date"), extracted.get("amount_cents"),
                extracted.get("identifier_type"), extracted.get("identifier_value"),
                extracted.get("full_name"), extracted.get("tax_id"), extracted.get("origin_bank"),
                extracted.get("destination_account_key"), reason, ocr_text,
                json.dumps({
                    "mode": "human_visual_review" if human_review else "deterministic_ocr_rules",
                    "human_validated": bool(human_review),
                }),
                json.dumps(evidence),
                f"{EXTRACTOR_VERSION}+human-review" if human_review else EXTRACTOR_VERSION,
            ),
        )
        transition(
            conn,
            job["document_id"],
            status,
            actor="tickets-worker",
            reason=reason,
            evidence=evidence,
        )
        queue_shadow_action(conn, job["document_id"], status, reason)
        conn.execute(
            "UPDATE processing_jobs SET status='DONE',locked_at=NULL,locked_by=NULL,updated_at=now() WHERE job_id=%s",
            (job["job_id"],),
        )
        conn.commit()
    generate()


def fail(job: dict, exc: Exception) -> None:
    final = job["attempts"] >= MAX_ATTEMPTS
    job_status = "FAILED" if final else "RETRY"
    document_status = "ERROR_FINAL" if final else "ERROR_RETRYABLE"
    wait_seconds = min(300, 5 * (2 ** max(job["attempts"] - 1, 0)))
    message = f"{type(exc).__name__}: {exc}"
    with connection() as conn:
        transition(
            conn,
            job["document_id"],
            document_status,
            actor="tickets-worker",
            reason=message,
            evidence={"attempt": job["attempts"], "traceback": traceback.format_exc()[-4000:]},
        )
        conn.execute(
            """UPDATE processing_jobs SET status=%s,last_error=%s,locked_at=NULL,locked_by=NULL,
               available_at=now()+(%s * interval '1 second'),updated_at=now() WHERE job_id=%s""",
            (job_status, message, wait_seconds, job["job_id"]),
        )
        conn.execute(
            "UPDATE ticket_documents SET last_error=%s WHERE document_id=%s",
            (message, job["document_id"]),
        )
        conn.commit()


def main() -> None:
    while True:
        job = claim()
        if job is None:
            time.sleep(1)
            continue
        try:
            process(job)
        except Exception as exc:
            fail(job, exc)


if __name__ == "__main__":
    main()
