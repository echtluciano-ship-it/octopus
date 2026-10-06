from __future__ import annotations

import argparse
from pathlib import Path

from jarvis.core.audit_log import AuditLog
from jarvis.core.coordinator import JarvisCoordinator
from jarvis.core.policy import PermissionPolicy
from jarvis.scripts.build_test_db import build_test_database
from jarvis.tools.octopus_reader import OctopusReader


ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "data" / "octopus_test.db"
DEFAULT_AUDIT = ROOT / "logs" / "jarvis_audit.db"


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS / OCTOPUS isolated laboratory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init-test", help="Create synthetic TEST data")
    init_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    ask_parser = subparsers.add_parser("ask", help="Run one audited read-only request")
    ask_parser.add_argument("request")
    ask_parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    ask_parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    args = parser.parse_args()

    if args.command == "init-test":
        build_test_database(args.db)
        print(f"TEST database created: {args.db.resolve()}")
        return

    reader = OctopusReader(args.db, laboratory=True)
    coordinator = JarvisCoordinator(reader, PermissionPolicy(), AuditLog(args.audit))
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
