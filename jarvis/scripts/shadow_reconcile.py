from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from jarvis.tools.octopus_reader import OctopusReader
from metrics import executive_summary


def _read_factory(db_path: Path):
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"

    def read(query: str, params: tuple = ()) -> pd.DataFrame:
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.execute("PRAGMA query_only=ON")
            return pd.read_sql_query(query, conn, params=params)

    return read


def _close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0, abs_tol=0.01)


def reconcile_months(db_path: Path, as_of: date, months: list[str] | None = None) -> dict[str, Any]:
    db_path = Path(db_path).resolve()
    reader = OctopusReader(db_path, environment="shadow", as_of=as_of)
    if months is None:
        with reader._connection() as conn:
            months = [
                row[0]
                for row in conn.execute(
                    "SELECT month FROM billing_operations UNION SELECT month FROM rentability_operations "
                    "ORDER BY month"
                )
            ]

    read = _read_factory(db_path)
    results = []
    for month in months:
        shadow = reader.month_summary(month).data
        billing, rent = executive_summary(month, as_of, read=read)
        expected = {
            "billing_total": float(billing.iloc[0]["facturacion"]),
            "billing_records": int(billing.iloc[0]["registros"]),
            "validated_billing": float(rent.iloc[0]["facturacion_neta_rentabilidad"]),
            "octopus_profit": float(rent.iloc[0]["ganancia_octopus"]),
            "valid_operations": int(rent.iloc[0]["operaciones"]),
        }
        expected["profitability_pct"] = (
            expected["octopus_profit"] / expected["validated_billing"] * 100
            if expected["validated_billing"]
            else None
        )
        differences = []
        for field, value in expected.items():
            actual = shadow[field]
            if value is None:
                if actual is not None:
                    differences.append(f"{field}: {actual} != None")
            elif isinstance(value, float):
                if not _close(actual, value):
                    differences.append(f"{field}: {actual} != {value}")
            elif actual != value:
                differences.append(f"{field}: {actual} != {value}")
        results.append({"month": month, "status": "OK" if not differences else "DIFFERENCE", "values": shadow, "differences": differences})

    return {
        "as_of": as_of.isoformat(),
        "database": str(db_path),
        "months_checked": len(results),
        "status": "OK" if all(item["status"] == "OK" for item in results) else "DIFFERENCE",
        "results": results,
    }


def write_report(report: dict[str, Any], output: Path) -> None:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
