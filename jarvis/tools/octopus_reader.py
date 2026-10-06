from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from jarvis.core.contracts import NeedsReview, ToolResult


VALID_RENTABILITY = (
    "status LIKE 'OK%' AND billed_amount > 0 AND octopus_profit IS NOT NULL"
)


class OctopusReader:
    """A narrow read-only facade. It never accepts raw SQL from an agent."""

    def __init__(self, db_path: Path, *, laboratory: bool = True) -> None:
        self.db_path = Path(db_path).resolve()
        if not self.db_path.exists():
            raise FileNotFoundError(self.db_path)
        if laboratory and "test" not in self.db_path.name.lower():
            raise ValueError("JARVIS TEST Lab only accepts a database whose name contains 'test'")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        uri = self.db_path.as_uri() + "?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def month_summary(self, month: str) -> ToolResult:
        with self._connection() as conn:
            billing = conn.execute(
                "SELECT COUNT(*) records, COALESCE(SUM(net_amount),0) total "
                "FROM billing_operations WHERE month=? AND net_amount > 0",
                (month,),
            ).fetchone()
            rent = conn.execute(
                f"SELECT COUNT(*) operations, COALESCE(SUM(billed_amount),0) net, "
                f"COALESCE(SUM(octopus_profit),0) profit FROM rentability_operations "
                f"WHERE month=? AND {VALID_RENTABILITY}",
                (month,),
            ).fetchone()
            operation_keys = [
                row[0]
                for row in conn.execute(
                    f"SELECT operation_key FROM rentability_operations WHERE month=? "
                    f"AND {VALID_RENTABILITY} ORDER BY operation_key",
                    (month,),
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
        with self._connection() as conn:
            billing = [
                dict(row)
                for row in conn.execute(
                    "SELECT billing_id,net_amount FROM billing_operations "
                    "WHERE month=? AND net_amount > 0 ORDER BY billing_id",
                    (month,),
                )
            ]
            operations = [
                dict(row)
                for row in conn.execute(
                    f"SELECT operation_key,billed_amount,octopus_profit FROM rentability_operations "
                    f"WHERE month=? AND {VALID_RENTABILITY} ORDER BY operation_key",
                    (month,),
                )
            ]
        return {"billing": billing, "operations": operations}

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
