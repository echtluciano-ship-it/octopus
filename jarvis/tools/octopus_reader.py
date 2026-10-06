from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from jarvis.core.contracts import NeedsReview, ToolResult


VALID_RENTABILITY = (
    "status LIKE 'OK%' AND billed_amount > 0 AND octopus_profit IS NOT NULL"
)


class OctopusReader:
    """A narrow read-only facade. It never accepts raw SQL from an agent."""

    def __init__(
        self,
        db_path: Path,
        *,
        environment: str = "test",
        as_of: date | None = None,
    ) -> None:
        self.db_path = Path(db_path).resolve()
        self.environment = environment
        self.as_of = as_of or date.today()
        if not self.db_path.exists():
            raise FileNotFoundError(self.db_path)
        required_marker = {"test": "test", "shadow": "shadow"}.get(environment)
        if required_marker is None:
            raise ValueError("JARVIS only accepts the TEST or SHADOW environment")
        if required_marker not in self.db_path.name.lower():
            raise ValueError(
                f"JARVIS {environment.upper()} only accepts a database whose name "
                f"contains {required_marker!r}"
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        uri = self.db_path.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        try:
            yield conn
        finally:
            conn.close()

    def month_summary(self, month: str) -> ToolResult:
        billing_where, billing_params = self._period_filter("billing", month)
        rent_where, rent_params = self._period_filter("rentability", month)
        with self._connection() as conn:
            billing = conn.execute(
                "SELECT COUNT(*) records, COALESCE(SUM(net_amount),0) total "
                f"FROM billing_operations WHERE {billing_where}",
                billing_params,
            ).fetchone()
            rent = conn.execute(
                f"SELECT COUNT(*) operations, COALESCE(SUM(billed_amount),0) net, "
                f"COALESCE(SUM(octopus_profit),0) profit FROM rentability_operations "
                f"WHERE {rent_where}",
                rent_params,
            ).fetchone()
            operation_keys = [
                row[0]
                for row in conn.execute(
                    f"SELECT operation_key FROM rentability_operations WHERE {rent_where} "
                    f"ORDER BY operation_key",
                    rent_params,
                )
            ]
        net = float(rent["net"])
        profit = float(rent["profit"])
        return ToolResult(
            tool="octopus.month_summary",
            data={
                "month": month,
                "billing_total": float(billing["total"]),
                "billing_records": int(billing["records"]),
                "validated_billing": net,
                "octopus_profit": profit,
                "profitability_pct": profit / net * 100 if net else None,
                "valid_operations": int(rent["operations"]),
            },
            evidence=[f"operation:{key}" for key in operation_keys],
        )

    def client_snapshot(self, client_name: str) -> ToolResult:
        with self._connection() as conn:
            client = conn.execute(
                "SELECT client_key, display_name FROM clients "
                "WHERE lower(display_name)=lower(?) OR lower(client_key)=lower(?)",
                (client_name, client_name),
            ).fetchone()
            if client is None:
                raise NeedsReview(f"Client not found: {client_name}")
            rows = conn.execute(
                f"SELECT operation_key,channel,month,operation_date,billed_amount,"
                f"octopus_profit,source_drive_id FROM rentability_operations "
                f"WHERE client_key=? AND {VALID_RENTABILITY} ORDER BY operation_date",
                (client["client_key"],),
            ).fetchall()
        net = sum(float(row["billed_amount"]) for row in rows)
        profit = sum(float(row["octopus_profit"]) for row in rows)
        return ToolResult(
            tool="octopus.client_snapshot",
            data={
                "client_key": client["client_key"],
                "display_name": client["display_name"],
                "validated_billing": net,
                "octopus_profit": profit,
                "profitability_pct": profit / net * 100 if net else None,
                "valid_operations": len(rows),
                "last_operation": rows[-1]["operation_date"] if rows else None,
                "months": sorted({row["month"] for row in rows}),
                "channels": sorted({row["channel"] for row in rows}),
            },
            evidence=[
                f"operation:{row['operation_key']}|drive:{row['source_drive_id']}" for row in rows
            ],
        )

    def review_cases(self, limit: int = 20) -> ToolResult:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT operation_key,client_name,channel,month,source_file,source_drive_id "
                "FROM rentability_operations WHERE status='REVISION' "
                "ORDER BY month,client_name LIMIT ?",
                (limit,),
            ).fetchall()
        cases = [dict(row) for row in rows]
        return ToolResult(
            tool="octopus.review_cases",
            data={"count": len(cases), "cases": cases},
            evidence=[
                f"operation:{row['operation_key']}|drive:{row['source_drive_id']}" for row in rows
            ],
        )

    def audit_month_components(self, month: str) -> dict:
        billing_where, billing_params = self._period_filter("billing", month)
        rent_where, rent_params = self._period_filter("rentability", month)
        with self._connection() as conn:
            billing = [
                dict(row)
                for row in conn.execute(
                    "SELECT id AS billing_id,net_amount FROM billing_operations "
                    f"WHERE {billing_where} ORDER BY id",
                    billing_params,
                )
            ]
            operations = [
                dict(row)
                for row in conn.execute(
                    f"SELECT operation_key,billed_amount,octopus_profit FROM rentability_operations "
                    f"WHERE {rent_where} ORDER BY operation_key",
                    rent_params,
                )
            ]
        return {"billing": billing, "operations": operations}

    def _period_filter(self, kind: str, month: str) -> tuple[str, tuple]:
        current_month = self.as_of.strftime("%Y-%m")
        validity = {
            "billing": "net_amount IS NOT NULL AND net_amount > 0",
            "rentability": VALID_RENTABILITY,
        }[kind]
        where = f"month=? AND {validity}"
        params: list[str] = [month]
        if month > current_month:
            where += " AND 0"
        elif month == current_month:
            if kind == "billing":
                where += " AND load_date <= ? AND period_date <= ?"
                params.extend((self.as_of.isoformat(), self.as_of.isoformat()))
            else:
                where += " AND operation_date <= ?"
                params.append(self.as_of.isoformat())
        return where, tuple(params)

    def audit_client_components(self, client_key: str) -> list[dict]:
        with self._connection() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    f"SELECT operation_key,channel,month,operation_date,billed_amount,"
                    f"octopus_profit,status,source_drive_id FROM "
                    f"rentability_operations WHERE client_key=? AND {VALID_RENTABILITY} "
                    f"ORDER BY operation_key",
                    (client_key,),
                )
            ]

    def audit_review_components(self, limit: int) -> list[dict]:
        with self._connection() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT operation_key,client_name,channel,month,source_file,source_drive_id "
                    "FROM rentability_operations WHERE status='REVISION' "
                    "ORDER BY month,client_name LIMIT ?",
                    (limit,),
                )
            ]
