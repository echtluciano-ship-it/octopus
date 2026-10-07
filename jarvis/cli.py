from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from jarvis.core.audit_log import AuditLog
from jarvis.core.coordinator import JarvisCoordinator
from jarvis.core.policy import PermissionPolicy
from jarvis.scripts.build_test_db import build_test_database
from jarvis.scripts.create_shadow_snapshot import create_shadow_snapshot
from jarvis.scripts.shadow_observe import observe_shadow, write_observation_report
from jarvis.scripts.shadow_cycle import run_shadow_cycle, write_cycle_report
from jarvis.scripts.shadow_reconcile import reconcile_months, write_report
from jarvis.tools.octopus_reader import OctopusReader


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "octopus_test.db"
DEFAULT_AUDIT = ROOT / "logs" / "jarvis_audit.db"
DEFAULT_SHADOW_DB = ROOT / "data" / "octopus_shadow.db"
DEFAULT_SHADOW_MANIFEST = ROOT / "data" / "octopus_shadow_manifest.json"
DEFAULT_SHADOW_AUDIT = ROOT / "logs" / "jarvis_shadow_audit.db"
DEFAULT_SHADOW_REPORT = ROOT / "logs" / "octopus_shadow_reconciliation.json"
DEFAULT_SHADOW_OBSERVATION = ROOT / "logs" / "octopus_shadow_observation.json"
DEFAULT_SHADOW_CYCLE_REPORT = ROOT / "logs" / "octopus_shadow_cycle.json"
DEFAULT_SHADOW_HISTORY = ROOT / "logs" / "octopus_shadow_history.db"
SHADOW_POLICY = ROOT / "config" / "permissions.shadow.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS / OCTOPUS isolated laboratory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init-test", help="Create synthetic TEST data")
    init_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    shadow_parser = subparsers.add_parser("init-shadow", help="Create a verified read-only snapshot")
    shadow_parser.add_argument("--source", type=Path, required=True)
    shadow_parser.add_argument("--db", type=Path, default=DEFAULT_SHADOW_DB)
    shadow_parser.add_argument("--manifest", type=Path, default=DEFAULT_SHADOW_MANIFEST)
    reconcile_parser = subparsers.add_parser("reconcile-shadow", help="Compare SHADOW with OCTOPUS metrics")
    reconcile_parser.add_argument("--db", type=Path, default=DEFAULT_SHADOW_DB)
    reconcile_parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    reconcile_parser.add_argument("--report", type=Path, default=DEFAULT_SHADOW_REPORT)
    observe_parser = subparsers.add_parser("observe-shadow", help="Run the full audited SHADOW suite")
    observe_parser.add_argument("--db", type=Path, default=DEFAULT_SHADOW_DB)
    observe_parser.add_argument("--manifest", type=Path, default=DEFAULT_SHADOW_MANIFEST)
    observe_parser.add_argument("--audit", type=Path, default=DEFAULT_SHADOW_AUDIT)
    observe_parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    observe_parser.add_argument("--report", type=Path, default=DEFAULT_SHADOW_OBSERVATION)
    cycle_parser = subparsers.add_parser("shadow-cycle", help="Refresh, compare and audit SHADOW")
    cycle_parser.add_argument("--source", type=Path, required=True)
    cycle_parser.add_argument("--db", type=Path, default=DEFAULT_SHADOW_DB)
    cycle_parser.add_argument("--manifest", type=Path, default=DEFAULT_SHADOW_MANIFEST)
    cycle_parser.add_argument("--audit", type=Path, default=DEFAULT_SHADOW_AUDIT)
    cycle_parser.add_argument("--history", type=Path, default=DEFAULT_SHADOW_HISTORY)
    cycle_parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    cycle_parser.add_argument("--report", type=Path, default=DEFAULT_SHADOW_CYCLE_REPORT)
    ask_parser = subparsers.add_parser("ask", help="Run one audited read-only request")
    ask_parser.add_argument("request")
    ask_parser.add_argument("--environment", choices=("test", "shadow"), default="test")
    ask_parser.add_argument("--db", type=Path)
    ask_parser.add_argument("--audit", type=Path)
    args = parser.parse_args()

    if args.command == "init-test":
        build_test_database(args.db)
        print(f"TEST database created: {args.db.resolve()}")
        return

    if args.command == "init-shadow":
        result = create_shadow_snapshot(args.source, args.db, args.manifest)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return

    if args.command == "reconcile-shadow":
        report = reconcile_months(args.db, args.as_of)
        write_report(report, args.report)
        print(json.dumps(report, indent=2, ensure_ascii=True))
        if report["status"] != "OK":
            raise SystemExit(1)
        return

    if args.command == "observe-shadow":
        report = observe_shadow(
            args.db,
            args.manifest,
            SHADOW_POLICY,
            args.audit,
            args.as_of,
        )
        write_observation_report(report, args.report)
        print(json.dumps(report, indent=2, ensure_ascii=True))
        if report["status"] == "BLOCKED":
            raise SystemExit(1)
        return

    if args.command == "shadow-cycle":
        report = run_shadow_cycle(
            source=args.source,
            db_path=args.db,
            manifest_path=args.manifest,
            policy_path=SHADOW_POLICY,
            audit_path=args.audit,
            history_path=args.history,
            as_of=args.as_of,
        )
        write_cycle_report(report, args.report)
        summary = {
            "cycle_id": report["cycle_id"],
            "status": report["status"],
            "source_unchanged": report["snapshot"]["source_unchanged"],
            "months_checked": report["observation"]["reconciliation"]["months_checked"],
            "clients_checked": report["observation"]["observations"]["clients_total"],
            "affected_months": report["drift"]["affected_months"],
            "affected_clients": report["drift"]["affected_clients"],
            "reviews_added": report["drift"]["reviews_added"],
            "reviews_resolved": report["drift"]["reviews_resolved"],
            "external_actions_executed": report["external_actions_executed"],
        }
        print(json.dumps(summary, indent=2, ensure_ascii=True))
        if report["status"] == "BLOCKED":
            raise SystemExit(1)
        return

    environment = args.environment
    db_path = args.db or (DEFAULT_SHADOW_DB if environment == "shadow" else DEFAULT_DB)
    audit_path = args.audit or (DEFAULT_SHADOW_AUDIT if environment == "shadow" else DEFAULT_AUDIT)
    policy = PermissionPolicy(SHADOW_POLICY) if environment == "shadow" else PermissionPolicy()
    reader = OctopusReader(db_path, environment=environment)
    coordinator = JarvisCoordinator(reader, policy, AuditLog(audit_path))
    response = coordinator.handle(args.request)
    print(response.answer)
    print(f"Estado: {response.status}")
    print(f"Auditoria: {response.run_id}")
    if response.evidence:
        print("Evidencia:")
        for item in response.evidence:
            print(f"- {item}")


if __name__ == "__main__":
    main()
