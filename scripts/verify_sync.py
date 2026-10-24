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
from billing_freshness import reconcile_billing_load_date, verify_live_billing_source
from sync_checks import reconcile_database, verify_manifest, write_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile all OCTOPUS indicators before publication.")
    parser.add_argument("--write-manifest", action="store_true")
    billing_check = parser.add_mutually_exclusive_group()
    billing_check.add_argument("--check-live-billing", dest="check_live_billing", action="store_true")
    billing_check.add_argument("--skip-live-billing", dest="check_live_billing", action="store_false")
    parser.set_defaults(check_live_billing=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=business_today())
    args = parser.parse_args()
    if not args.write_manifest:
        verify_manifest(APP_DIR)
    live_hash = verify_live_billing_source(APP_DIR) if args.check_live_billing else None
    with closing(sqlite3.connect((APP_DIR / "octopus.db").as_uri() + "?mode=ro", uri=True)) as conn:
        report = reconcile_database(conn, args.as_of)
    daily = reconcile_billing_load_date(APP_DIR, args.as_of) if args.check_live_billing else None
    if args.write_manifest:
        write_manifest(APP_DIR, report)
    if args.check_live_billing:
        print(f"Live billing source verified: {live_hash}")
        print(f"Billing load date reconciled: {daily}")
    print(f"Reconciled {len(report['months'])} months; {report['published_clients']} published clients")
    for month, row in report["months"].items():
        if month >= "2026-07":
            print(month, {k: v for k, v in row.items() if 'ranking' not in k})


if __name__ == "__main__":
    main()
