from __future__ import annotations

import argparse

from service.db import connection
from service.workflow import transition


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue persisted TEST tickets again.")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--source-batch")
    target.add_argument("--document-id", type=int)
    args = parser.parse_args()
    with connection() as conn:
        if args.document_id is not None:
            rows = conn.execute(
                "SELECT document_id FROM ticket_documents WHERE document_id=%s",
                (args.document_id,),
            ).fetchall()
            label = f"documento {args.document_id}"
            evidence = {"document_id": args.document_id}
        else:
            rows = conn.execute(
                "SELECT document_id FROM ticket_documents WHERE source_batch=%s ORDER BY document_id",
                (args.source_batch,),
            ).fetchall()
            label = f"lote {args.source_batch}"
            evidence = {"source_batch": args.source_batch}
        for row in rows:
            transition(
                conn,
                row["document_id"],
                "QUEUED",
                actor="dataset-reprocess",
                reason=f"Reprocesamiento controlado del {label}.",
                evidence=evidence,
            )
            conn.execute(
                """UPDATE processing_jobs
                      SET status='PENDING',available_at=now(),locked_at=NULL,locked_by=NULL,
                          last_error=NULL,updated_at=now()
                    WHERE document_id=%s""",
                (row["document_id"],),
            )
        conn.commit()
    print({**evidence, "queued": len(rows)})


if __name__ == "__main__":
    main()
