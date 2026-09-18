from __future__ import annotations

import argparse
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

from data_access import business_today
from sync_checks import reconcile_database, verify_manifest, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile all OCTOPUS indicators before publication.")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--as-of", type=date.fromisoformat, default=business_today())
    args = parser.parse_args()
    if not args.write_manifest:
        verify_manifest(APP_DIR)
    with closing(sqlite3.connect((APP_DIR / "octopus.db").as_uri() + "?mode=ro", uri=True)) as conn:
        report = reconcile_database(conn, args.as_of)
    if args.write_manifest:
        write_manifest(APP_DIR, report)
    print(f"Reconciled {len(report['months'])} months; {report['published_clients']} published clients")
    for month, row in report["months"].items():
        if month >= "2026-07":
            print(month, {k: v for k, v in row.items() if 'ranking' not in k})


if __name__ == "__main__":
    main()
