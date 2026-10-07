from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.scripts.create_shadow_snapshot import create_shadow_snapshot, sha256_file
from jarvis.scripts.shadow_observe import observe_shadow
from jarvis.tools.octopus_reader import OctopusReader


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def capture_shadow_state(db_path: Path, as_of: date) -> dict[str, Any]:
    reader = OctopusReader(db_path, environment="shadow", as_of=as_of)
    with reader._connection() as conn:
        tables = ("clients", "billing_operations", "rentability_operations", "source_documents")
        counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
        months = [
            row[0]
            for row in conn.execute(
                "SELECT month FROM billing_operations WHERE month IS NOT NULL "
                "UNION SELECT month FROM rentability_operations WHERE month IS NOT NULL "
                "ORDER BY month"
            )
        ]
        client_rows = conn.execute(
            "SELECT client_key,COUNT(*) AS operations,SUM(billed_amount) AS billing," 
            "SUM(octopus_profit) AS profit,MAX(operation_date) AS last_operation "
            "FROM rentability_operations WHERE status LIKE 'OK%' AND billed_amount > 0 "
            "AND octopus_profit IS NOT NULL GROUP BY client_key ORDER BY client_key"
        ).fetchall()
        review_keys = [
            row[0]
            for row in conn.execute(
                "SELECT operation_key FROM rentability_operations WHERE status='REVISION' "
                "ORDER BY operation_key"
            )
        ]

    month_state = {}
    for month in months:
        data = reader.month_summary(month).data
        month_state[month] = {
            "billing_total": data["billing_total"],
            "billing_records": data["billing_records"],
            "validated_billing": data["validated_billing"],
            "octopus_profit": data["octopus_profit"],
            "valid_operations": data["valid_operations"],
        }
    clients = {
        row["client_key"]: {
            "operations": int(row["operations"]),
            "billing": float(row["billing"]),
            "profit": float(row["profit"]),
            "last_operation": row["last_operation"],
        }
        for row in client_rows
    }
    return {
        "snapshot_sha256": sha256_file(db_path),
        "table_counts": counts,
        "months": month_state,
        "clients": clients,
        "review_keys": review_keys,
    }


def compare_states(previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
    if previous is None:
        return {
            "baseline": True,
            "table_deltas": current["table_counts"],
            "affected_months": sorted(current["months"]),
            "affected_clients": sorted(current["clients"]),
            "reviews_added": current["review_keys"],
            "reviews_resolved": [],
        }

    tables = sorted(set(previous["table_counts"]) | set(current["table_counts"]))
    months = sorted(set(previous["months"]) | set(current["months"]))
    clients = sorted(set(previous["clients"]) | set(current["clients"]))
    previous_reviews = set(previous["review_keys"])
    current_reviews = set(current["review_keys"])
    return {
        "baseline": False,
        "table_deltas": {
            table: current["table_counts"].get(table, 0) - previous["table_counts"].get(table, 0)
            for table in tables
        },
        "affected_months": [
            month for month in months if previous["months"].get(month) != current["months"].get(month)
        ],
        "affected_clients": [
            client for client in clients if previous["clients"].get(client) != current["clients"].get(client)
        ],
        "reviews_added": sorted(current_reviews - previous_reviews),
        "reviews_resolved": sorted(previous_reviews - current_reviews),
    }


def _load_previous_state(db_path: Path, manifest_path: Path, as_of: date) -> dict[str, Any] | None:
    db_path = Path(db_path)
    manifest_path = Path(manifest_path)
    if not db_path.is_file() or not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256_file(db_path) != manifest.get("snapshot_sha256"):
        return None
    return capture_shadow_state(db_path, as_of)


def record_cycle(history_path: Path, report: dict[str, Any]) -> None:
    history_path = Path(history_path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(history_path)) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS shadow_cycles (
                cycle_id TEXT PRIMARY KEY,
                created_at_utc TEXT NOT NULL,
                as_of TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                snapshot_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                report_json TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS shadow_cycles_no_update
            BEFORE UPDATE ON shadow_cycles BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            CREATE TRIGGER IF NOT EXISTS shadow_cycles_no_delete
            BEFORE DELETE ON shadow_cycles BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            """
        )
        conn.execute(
            "INSERT INTO shadow_cycles VALUES (?,?,?,?,?,?,?)",
            (
                report["cycle_id"],
                report["created_at_utc"],
                report["as_of"],
                report["snapshot"]["source_sha256_after"],
                report["snapshot"]["snapshot_sha256"],
                report["status"],
                json.dumps(report, ensure_ascii=True, sort_keys=True),
            ),
        )


def run_shadow_cycle(
    *,
    source: Path,
    db_path: Path,
    manifest_path: Path,
    policy_path: Path,
    audit_path: Path,
    history_path: Path,
    as_of: date,
) -> dict[str, Any]:
    previous = _load_previous_state(db_path, manifest_path, as_of)
    snapshot = create_shadow_snapshot(source, db_path, manifest_path)
    observation = observe_shadow(db_path, manifest_path, policy_path, audit_path, as_of)
    current = capture_shadow_state(db_path, as_of)
    drift = compare_states(previous, current)
    report = {
        "cycle_id": str(uuid.uuid4()),
        "created_at_utc": _utc_now(),
        "as_of": as_of.isoformat(),
        "status": observation["status"],
        "snapshot": snapshot,
        "observation": observation,
        "drift": drift,
        "external_actions_executed": 0,
    }
    record_cycle(history_path, report)
    return report


def write_cycle_report(report: dict[str, Any], output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
