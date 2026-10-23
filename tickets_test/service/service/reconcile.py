from __future__ import annotations

from service.config import settings
from service.db import connection


def reconciliation() -> dict:
    allowed_groups = list(settings.allowed_group_ids)
    with connection() as conn:
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(DISTINCT event_id) FROM inbound_messages
                WHERE expected_attachments > 0 OR group_id = ANY(%s)) AS events_received,
              (SELECT COUNT(*) FROM ingress_events
                WHERE event_type<>'messages.upsert') AS historical_system_events,
              (SELECT COUNT(*) FROM inbound_messages
                WHERE expected_attachments > 0 OR group_id = ANY(%s)) AS messages_received,
              (SELECT COUNT(*) FROM inbound_messages
                WHERE expected_attachments = 0 AND NOT (group_id = ANY(%s))) AS ignored_out_of_scope_messages,
              (SELECT COALESCE(SUM(expected_attachments),0) FROM inbound_messages
                WHERE expected_attachments > 0 OR group_id = ANY(%s)) AS documents_expected,
              (SELECT COUNT(*) FROM ticket_documents) AS documents_stored,
              (SELECT COUNT(*) FROM ticket_documents WHERE status IN
                ('READY_FOR_SHEET','SHEET_GENERATED','SHADOW_COMPARED')) AS processed,
              (SELECT COUNT(*) FROM ticket_documents WHERE status='DUPLICATE_CONFIRMED') AS duplicates,
              (SELECT COUNT(*) FROM ticket_documents WHERE status IN
                ('REVIEW','WRONG_ACCOUNT_REVIEW','CHECK_REVIEW')) AS review,
              (SELECT COUNT(*) FROM ticket_documents WHERE status IN
                ('ERROR_RETRYABLE','ERROR_FINAL')) AS document_errors,
              (SELECT COUNT(*) FROM ingest_failures
                WHERE resolved_at IS NULL AND status IN ('ERROR_RETRYABLE','ERROR_FINAL')) AS ingest_errors,
              (SELECT COUNT(*) FROM ticket_documents WHERE status IN
                ('ORIGINAL_STORED','QUEUED','PROCESSING','EXTRACTED')) AS in_progress
            """,
            (allowed_groups, allowed_groups, allowed_groups, allowed_groups),
        ).fetchone()
    result = dict(row)
    result["errors"] = result["document_errors"] + result["ingest_errors"]
    result["documents_missing"] = max(
        result["documents_expected"] - result["documents_stored"] - result["ingest_errors"],
        0,
    )
    result["document_equation_balanced"] = result["documents_stored"] == (
        result["processed"]
        + result["duplicates"]
        + result["review"]
        + result["document_errors"]
        + result["in_progress"]
    )
    result["ingest_balanced"] = result["documents_expected"] == (
        result["documents_stored"] + result["ingest_errors"]
    )
    result["status"] = "OK" if result["document_equation_balanced"] and result["ingest_balanced"] else "DIFFERENCE"
    return result
