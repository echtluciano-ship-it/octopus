from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

import metrics


SOURCE_FILES = (
    "data/FACTURACION OCTOPUS.xlsx",
    "data/billing_source.json",
    "manual_rentability_operations.csv",
    "client_aliases.csv",
    "source_documents.csv",
)


def sha256(path: Path) -> str:
    content = path.read_bytes()
    if path.suffix.lower() in {".csv", ".json"}:
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def same_amount(actual, expected, label: str) -> None:
    if not math.isclose(float(actual or 0), float(expected or 0), rel_tol=0, abs_tol=0.01):
        raise ValueError(f"{label}: {actual} != {expected}")


def reconcile_database(conn: sqlite3.Connection, as_of: date) -> dict:
    def read(query, params=()):
        return pd.read_sql_query(query, conn, params=params)

    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("SQLite integrity check failed")
    all_rent = read("SELECT * FROM rentability_operations")
    all_bill = read("SELECT * FROM billing_operations")
    valid = all_rent[
        all_rent.status.str.startswith("OK")
        & (all_rent.billed_amount > 0)
        & all_rent.octopus_profit.notna()
    ]
    billed = all_bill[all_bill.net_amount.notna() & (all_bill.net_amount > 0)]
    if valid.operation_key.duplicated().any():
        raise ValueError("An operation identity is being counted more than once")
    source_conflicts = read(
        """SELECT d.drive_id FROM source_documents d
        JOIN rentability_operations r ON r.source_drive_id = d.drive_id
        WHERE d.status IN ('EXCLUIDO','DUPLICADO','NO_PROCESAR','REVISION')
        AND r.status LIKE 'OK%' AND r.billed_amount > 0 AND r.octopus_profit IS NOT NULL"""
    )
    if not source_conflicts.empty:
        raise ValueError(f"Source exclusions not respected: {source_conflicts.drive_id.tolist()}")

    monthly = read("SELECT * FROM monthly_metrics")
    if monthly.duplicated(["client_key", "channel", "month"]).any():
        raise ValueError("Repeated canonical client/channel/month in monthly_metrics")
    for row in monthly.itertuples(index=False):
        rr = valid[(valid.client_key == row.client_key) & (valid.channel == row.channel) & (valid.month == row.month)]
        bb = billed[(billed.client_key == row.client_key) & (billed.channel == row.channel) & (billed.month == row.month)]
        label = f"monthly_metrics {row.client_key}/{row.channel}/{row.month}"
        same_amount(row.rentability_billed, rr.billed_amount.sum(), label + " net")
        same_amount(row.octopus_profit, rr.octopus_profit.sum(), label + " profit")
        same_amount(row.billing_total, bb.net_amount.sum(), label + " billing")
        if row.rentability_operations != len(rr) or row.billing_operations != len(bb):
            raise ValueError(label + " counts differ")
        denominator = rr.billed_amount.sum()
        expected_pct = rr.octopus_profit.sum() / denominator if denominator else None
        if expected_pct is None:
            if pd.notna(row.rentability_pct):
                raise ValueError(label + " unexpected percentage")
        elif not math.isclose(row.rentability_pct, expected_pct, abs_tol=1e-12):
            raise ValueError(label + " percentage differs")

    months = sorted(set(all_bill.month.dropna()) | set(all_rent.month.dropna()))
    report = {"as_of": as_of.isoformat(), "months": {}, "published_clients": int(valid.client_key.nunique())}
    for month in months:
        if month > as_of.strftime("%Y-%m"):
            continue
        rr = valid[valid.month == month]
        bb = billed[billed.month == month]
        if month == as_of.strftime("%Y-%m"):
            rr = rr[rr.operation_date <= as_of.isoformat()]
            bb = bb[bb.load_date <= as_of.isoformat()]
        b_summary, r_summary = metrics.executive_summary(month, as_of, read)
        b_top = metrics.billing_ranking(month, -1, as_of, read)
        r_top = metrics.rentability_ranking(month, -1, as_of, read)
        for actual, expected, label in (
            (b_summary.iloc[0].facturacion, bb.net_amount.sum(), "billing total"),
            (r_summary.iloc[0].facturacion_neta_rentabilidad, rr.billed_amount.sum(), "valid net"),
            (r_summary.iloc[0].ganancia_octopus, rr.octopus_profit.sum(), "profit"),
            (b_top.facturacion.sum(), bb.net_amount.sum(), "billing ranking total"),
            (r_top.facturacion_validada.sum(), rr.billed_amount.sum(), "rent ranking net"),
            (r_top.ganancia_octopus.sum(), rr.octopus_profit.sum(), "rent ranking profit"),
        ):
            same_amount(actual, expected, f"{month} {label}")
        if int(b_summary.iloc[0].registros) != len(bb) or int(r_summary.iloc[0].operaciones) != len(rr):
            raise ValueError(f"{month}: executive counts differ")
        if b_top.client_key.duplicated().any() or r_top.client_key.duplicated().any():
            raise ValueError(f"{month}: repeated canonical client in ranking")
        for row in r_top.itertuples(index=False):
            group = rr[rr.client_key == row.client_key]
            same_amount(row.facturacion_validada, group.billed_amount.sum(), f"{month} {row.client_key} net")
            same_amount(row.ganancia_octopus, group.octopus_profit.sum(), f"{month} {row.client_key} profit")
            if not math.isclose(row.rentabilidad, group.octopus_profit.sum() / group.billed_amount.sum(), abs_tol=1e-12):
                raise ValueError(f"{month}: weighted profitability differs for {row.client_key}")
        for row in b_top.itertuples(index=False):
            same_amount(row.facturacion, bb.loc[bb.client_key == row.client_key, "net_amount"].sum(), f"{month} {row.client_key} billing")
        for limit in (5, 10, 20):
            pd.testing.assert_frame_equal(metrics.rentability_ranking(month, limit, as_of, read), r_top.head(limit))
            pd.testing.assert_frame_equal(metrics.billing_ranking(month, limit, as_of, read), b_top.head(limit))
        denominator = float(rr.billed_amount.sum())
        report["months"][month] = {
            "billing_total": round(float(bb.net_amount.sum()), 2),
            "billing_records": len(bb),
            "validated_net": denominator,
            "profit": float(rr.octopus_profit.sum()),
            "profitability": float(rr.octopus_profit.sum()) / denominator if denominator else None,
            "valid_operations": len(rr),
            "rentability_ranking": r_top.head(20).to_dict("records"),
            "billing_ranking": b_top.head(20).to_dict("records"),
        }

    # Client cards are all-time views; future-dated records remain in their trace.
    client_totals = read(f"""SELECT r.client_key, SUM(billed_amount) net, SUM(octopus_profit) profit, COUNT(*) n
        FROM (SELECT * FROM rentability_operations WHERE {metrics.VALID_RENTABILITY}) r
        JOIN clients c ON c.client_key=r.client_key GROUP BY r.client_key""")
    same_amount(client_totals.net.sum(), valid.billed_amount.sum(), "client cards net")
    same_amount(client_totals.profit.sum(), valid.octopus_profit.sum(), "client cards profit")
    if int(client_totals.n.sum()) != len(valid) or len(client_totals) != report["published_clients"]:
        raise ValueError("Client cards lost valid operations")
    report["valid_operations_all_dates"] = len(valid)
    report["operation_states"] = all_rent.status.value_counts().to_dict()
    return report


def write_manifest(app_dir: Path, report: dict) -> dict:
    manifest = {
        "database_sha256": sha256(app_dir / "octopus.db"),
        "source_sha256": {name: sha256(app_dir / name) for name in SOURCE_FILES},
        "controls": report,
    }
    (app_dir / "data_sync_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(app_dir: Path) -> dict:
    manifest = json.loads((app_dir / "data_sync_manifest.json").read_text(encoding="utf-8"))
    expected = {"octopus.db": manifest["database_sha256"], **manifest["source_sha256"]}
    for name, digest in expected.items():
        if sha256(app_dir / name) != digest:
            raise ValueError(f"{name} changed: rebuild and reconcile the snapshot before publishing")
    return manifest
