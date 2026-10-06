from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.core.audit_log import AuditLog
from jarvis.core.coordinator import JarvisCoordinator
from jarvis.core.policy import PermissionPolicy
from jarvis.scripts.create_shadow_snapshot import sha256_file
from jarvis.scripts.shadow_reconcile import reconcile_months
from jarvis.tools.octopus_reader import OctopusReader


def verify_shadow_manifest(db_path: Path, manifest_path: Path) -> dict[str, Any]:
    db_path = Path(db_path).resolve()
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    problems = []
    actual_snapshot_hash = sha256_file(db_path)
    if actual_snapshot_hash != manifest.get("snapshot_sha256"):
        problems.append("snapshot hash differs from its manifest")

    source_path = Path(str(manifest.get("source_path", "")))
    if not source_path.is_file():
        problems.append("source database is no longer available")
        current_source_hash = None
    else:
        current_source_hash = sha256_file(source_path)
        if current_source_hash != manifest.get("source_sha256_after"):
            problems.append("source database changed; create a fresh SHADOW snapshot")

    return {
        "approved": not problems,
        "problems": problems,
        "snapshot_sha256": actual_snapshot_hash,
        "source_sha256": current_source_hash,
    }


def observe_shadow(
    db_path: Path,
    manifest_path: Path,
    policy_path: Path,
    audit_path: Path,
    as_of: date,
) -> dict[str, Any]:
    verification = verify_shadow_manifest(db_path, manifest_path)
    if not verification["approved"]:
        return {
            "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "as_of": as_of.isoformat(),
            "status": "BLOCKED",
            "snapshot_verification": verification,
        }

    reader = OctopusReader(db_path, environment="shadow", as_of=as_of)
    coordinator = JarvisCoordinator(
        reader,
        PermissionPolicy(policy_path),
        AuditLog(audit_path),
    )
    reconciliation = reconcile_months(db_path, as_of)

    months = [item["month"] for item in reconciliation["results"]]
    monthly_runs = [coordinator.handle(f"Resumen {month}") for month in months]
    with reader._connection() as conn:
        client_keys = [
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT client_key FROM rentability_operations "
                "WHERE status LIKE 'OK%' AND billed_amount > 0 "
                "AND octopus_profit IS NOT NULL ORDER BY client_key"
            )
        ]
        valid_operations = int(
            conn.execute(
                "SELECT COUNT(*) FROM rentability_operations "
                "WHERE status LIKE 'OK%' AND billed_amount > 0 "
                "AND octopus_profit IS NOT NULL"
            ).fetchone()[0]
        )
        review_rows = [
            dict(row)
            for row in conn.execute(
                "SELECT operation_key,client_name,source_file,source_drive_id "
                "FROM rentability_operations WHERE status='REVISION' ORDER BY operation_key"
            )
        ]

    client_runs = [coordinator.handle(f"Ficha de {client_key}") for client_key in client_keys]
    review_run = coordinator.handle("Mostrar casos en revision")
    monthly_failures = [run.run_id for run in monthly_runs if run.status != "APPROVED"]
    client_failures = [run.run_id for run in client_runs if run.status != "APPROVED"]
    traceability_gaps = [
        {
            "operation_key": row["operation_key"],
            "client_name": row["client_name"],
            "source_file": row["source_file"],
            "problem": "REVIEW operation has no Drive ID",
        }
        for row in review_rows
        if not row["source_drive_id"]
    ]

    blocking = []
    if reconciliation["status"] != "OK":
        blocking.append("monthly reconciliation differs from OCTOPUS metrics")
    if monthly_failures:
        blocking.append("one or more monthly observations failed audit")
    if client_failures:
        blocking.append("one or more client observations failed audit")

    status = "BLOCKED" if blocking else ("OK_WITH_REVIEW" if traceability_gaps else "OK")
    return {
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "as_of": as_of.isoformat(),
        "status": status,
        "snapshot_verification": verification,
        "reconciliation": {
            "status": reconciliation["status"],
            "months_checked": reconciliation["months_checked"],
        },
        "observations": {
            "months_total": len(monthly_runs),
            "months_approved": len(monthly_runs) - len(monthly_failures),
            "month_failures": monthly_failures,
            "clients_total": len(client_runs),
            "clients_approved": len(client_runs) - len(client_failures),
            "client_failures": client_failures,
            "valid_operations_observed": valid_operations,
            "review_cases": len(review_rows),
            "review_queue_status": review_run.status,
        },
        "traceability_gaps": traceability_gaps,
        "blocking_problems": blocking,
        "external_actions_executed": 0,
    }


def write_observation_report(report: dict[str, Any], output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
