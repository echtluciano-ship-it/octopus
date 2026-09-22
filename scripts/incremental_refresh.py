from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

import data_loader
from sync_checks import reconcile_database, sha256, write_manifest


STATE_FILE = APP_DIR / "data" / "incremental_update_state.json"
MANIFEST_FILE = APP_DIR / "data_sync_manifest.json"
OPERATION_FIELDS = (
    "operation_key",
    "client_key",
    "client_name",
    "original_client_name",
    "channel",
    "operation_date",
    "month",
    "check_amount",
    "net_billing_amount",
    "billed_amount",
    "octopus_profit",
    "status",
    "operation_type",
    "source_file",
    "source_path",
    "reference",
    "note",
    "source_drive_id",
)


class FullRefreshRequired(RuntimeError):
    pass


def read_state(path: Path = STATE_FILE) -> dict:
    if not path.exists():
        return {"version": 1, "documents": {}, "official_sources": {}, "source_baseline": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def write_state(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def manual_rows(path: Path = data_loader.MANUAL_RENTABILITY_FILE) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def legacy_digest(rows: list[dict[str, str]]) -> str:
    legacy = [row for row in rows if not data_loader.extract_drive_id(row.get("source_path", ""))]
    payload = json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_baseline(state_path: Path = STATE_FILE) -> dict:
    state = read_state(state_path)
    state.setdefault("source_baseline", {})["manual_legacy_sha256"] = legacy_digest(manual_rows())
    state["source_baseline"]["recorded_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    write_state(state, state_path)
    return state


def same_value(left, right) -> bool:
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) or isinstance(right, (int, float)):
        try:
            return abs(float(left) - float(right)) <= 0.0001
        except (TypeError, ValueError):
            return False
    return str(left) == str(right)


def record_changed(record: dict, existing: sqlite3.Row) -> bool:
    return any(not same_value(record[field], existing[field]) for field in OPERATION_FIELDS)


def check_incremental_preconditions(state: dict, manifest: dict, rows: list[dict[str, str]]) -> None:
    if sha256(APP_DIR / "octopus.db") != manifest.get("database_sha256"):
        raise FullRefreshRequired("octopus.db no coincide con el ultimo manifest")
    for name in (
        "data/FACTURACION OCTOPUS.xlsx",
        "data/billing_source.json",
        "client_aliases.csv",
    ):
        expected = manifest.get("source_sha256", {}).get(name)
        if not expected or sha256(APP_DIR / name) != expected:
            raise FullRefreshRequired(f"cambio estructural en {name}")
    expected_legacy = state.get("source_baseline", {}).get("manual_legacy_sha256")
    if not expected_legacy or legacy_digest(rows) != expected_legacy:
        raise FullRefreshRequired("cambio en filas historicas sin Drive ID")


def refresh(state_path: Path = STATE_FILE) -> dict:
    started = time.perf_counter()
    state = read_state(state_path)
    if not MANIFEST_FILE.exists() or not (APP_DIR / "octopus.db").exists():
        raise FullRefreshRequired("falta base o manifest previo")
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    rows = manual_rows()
    check_incremental_preconditions(state, manifest, rows)

    data_loader.ALIAS_BY_KEY = data_loader.load_alias_map()
    current_records: dict[str, dict] = {}
    for row in rows:
        record = data_loader.manual_rentability_record(row)
        if record is None:
            continue
        drive_id = record["source_drive_id"]
        if not drive_id:
            continue
        if drive_id in current_records:
            raise FullRefreshRequired(f"Drive ID repetido en CSV manual: {drive_id}")
        current_records[drive_id] = record

    with closing(sqlite3.connect(APP_DIR / "octopus.db")) as baseline:
        baseline.row_factory = sqlite3.Row
        existing_rows = baseline.execute(
            f"SELECT {', '.join(OPERATION_FIELDS)} FROM rentability_operations "
            "WHERE COALESCE(source_drive_id, '') <> ''"
        ).fetchall()
        existing = {row["source_drive_id"]: row for row in existing_rows}
        if len(existing) != len(existing_rows):
            raise FullRefreshRequired("hay mas de una operacion para el mismo Drive ID")

    removed = set(existing) - set(current_records)
    if removed:
        raise FullRefreshRequired(
            "se quitaron operaciones persistidas: " + ", ".join(sorted(removed)[:5])
        )
    new_ids = {drive_id for drive_id in current_records if drive_id not in existing}
    updated_ids = {
        drive_id
        for drive_id, record in current_records.items()
        if drive_id in existing and record_changed(record, existing[drive_id])
    }
    changed_ids = new_ids | updated_ids
    source_documents_changed = (
        sha256(APP_DIR / "source_documents.csv")
        != manifest.get("source_sha256", {}).get("source_documents.csv")
    )
    manual_changed = (
        sha256(APP_DIR / "manual_rentability_operations.csv")
        != manifest.get("source_sha256", {}).get("manual_rentability_operations.csv")
    )
    if manual_changed and not changed_ids:
        raise FullRefreshRequired("cambio no explicado en manual_rentability_operations.csv")
    if not changed_ids and not source_documents_changed:
        return {
            "mode": "incremental",
            "changed": False,
            "new_operations": 0,
            "updated_operations": 0,
            "affected_clients": [],
            "affected_months": [],
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }

    fd, temporary = tempfile.mkstemp(prefix=".octopus-incremental-", suffix=".db", dir=APP_DIR)
    os.close(fd)
    shutil.copy2(APP_DIR / "octopus.db", temporary)
    try:
        with closing(sqlite3.connect(temporary)) as conn, conn:
            old_rows = []
            if changed_ids:
                placeholders = ", ".join("?" for _ in changed_ids)
                old_rows = conn.execute(
                    f"SELECT client_key, channel, month FROM rentability_operations "
                    f"WHERE source_drive_id IN ({placeholders})",
                    tuple(sorted(changed_ids)),
                ).fetchall()
                conn.execute(
                    f"DELETE FROM rentability_operations WHERE source_drive_id IN ({placeholders})",
                    tuple(sorted(changed_ids)),
                )
                data_loader.load_manual_rentability(conn, changed_ids)

            if source_documents_changed:
                conn.execute("DELETE FROM source_documents")
                data_loader.load_source_documents(conn)

            new_rows = []
            if changed_ids:
                placeholders = ", ".join("?" for _ in changed_ids)
                new_rows = conn.execute(
                    f"SELECT client_key, channel, month FROM rentability_operations "
                    f"WHERE source_drive_id IN ({placeholders})",
                    tuple(sorted(changed_ids)),
                ).fetchall()
            identities = {tuple(row) for row in old_rows + new_rows}
            client_keys = {row[0] for row in identities}
            data_loader.rebuild_clients(conn, client_keys)
            data_loader.rebuild_monthly_metrics(conn, identities)
            report = reconcile_database(
                conn,
                datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).date(),
            )
            conn.commit()
        os.replace(temporary, APP_DIR / "octopus.db")
        write_manifest(APP_DIR, report)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

    state = record_baseline(state_path)
    state["last_database_refresh"] = {
        "mode": "incremental",
        "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "new_operations": len(new_ids),
        "updated_operations": len(updated_ids),
    }
    write_state(state, state_path)
    return {
        "mode": "incremental",
        "changed": True,
        "new_operations": len(new_ids),
        "updated_operations": len(updated_ids),
        "affected_clients": sorted({row[0] for row in identities}),
        "affected_months": sorted({row[2] for row in identities}),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply only changed Drive-backed operations to OCTOPUS.")
    parser.add_argument("--state", type=Path, default=STATE_FILE)
    parser.add_argument("--record-baseline", action="store_true")
    args = parser.parse_args()
    if args.record_baseline:
        record_baseline(args.state)
        print(json.dumps({"mode": "baseline", "status": "ok"}, ensure_ascii=False))
        return
    try:
        print(json.dumps(refresh(args.state), ensure_ascii=False))
    except FullRefreshRequired as exc:
        print(json.dumps({"mode": "full_refresh_required", "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
