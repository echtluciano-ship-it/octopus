from __future__ import annotations

import argparse

from service.db import connection
from service.workflow import transition


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue a persisted TEST source batch again.")
    parser.add_argument("--source-batch", required=True)
    args = parser.parse_args()
    with connection() as conn:
        rows = conn.execute(
            "SELECT document_id FROM ticket_documents WHERE source_batch=%s ORDER BY document_id",
            (args.source_batch,),
        ).fetchall()
        for row in rows:
            transition(
                conn,
                row["document_id"],
                "QUEUED",
                actor="dataset-reprocess",
                reason=f"Reprocesamiento controlado del lote {args.source_batch}.",
                evidence={"source_batch": args.source_batch},
            )
            conn.execute(
                """UPDATE processing_jobs
                      SET status='PENDING',available_at=now(),locked_at=NULL,locked_by=NULL,
                          last_error=NULL,updated_at=now()
                    WHERE document_id=%s""",
                (row["document_id"],),
            )
        conn.commit()
    print({"source_batch": args.source_batch, "queued": len(rows)})


if __name__ == "__main__":
    main()
