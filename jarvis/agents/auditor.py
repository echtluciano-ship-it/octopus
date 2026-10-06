from __future__ import annotations

import math

from jarvis.core.contracts import AuditDecision, PlannedAction, ToolResult
from jarvis.tools.octopus_reader import OctopusReader


class OctopusAuditor:
    agent_id = "auditor"

    def __init__(self, reader: OctopusReader) -> None:
        self.reader = reader

    def verify(self, action: PlannedAction, result: ToolResult) -> AuditDecision:
        if action.intent == "month_summary":
            return self._month(action.arguments["month"], result)
        if action.intent == "client_snapshot":
            return self._client(result)
        if action.intent == "review_cases":
            return self._reviews(action.arguments["limit"], result)
        return AuditDecision(False, [], [f"Unsupported audit intent: {action.intent}"])

    def _month(self, month: str, result: ToolResult) -> AuditDecision:
        components = self.reader.audit_month_components(month)
        billing_total = sum(float(row["net_amount"]) for row in components["billing"])
        net = sum(float(row["billed_amount"]) for row in components["operations"])
        profit = sum(float(row["octopus_profit"]) for row in components["operations"])
        expected_pct = profit / net * 100 if net else None
        expected = {
            "billing_total": billing_total,
            "billing_records": len(components["billing"]),
            "validated_billing": net,
            "octopus_profit": profit,
            "profitability_pct": expected_pct,
            "valid_operations": len(components["operations"]),
        }
        problems = self._compare(result.data, expected)
        expected_evidence = {
            f"operation:{row['operation_key']}" for row in components["operations"]
        }
        if set(result.evidence) != expected_evidence:
            problems.append("monthly evidence does not match valid operations")
        checks = [
            "billing total recomputed from billing rows",
            "validated billing and profit recomputed from valid operations",
            "profitability recomputed as total profit / total validated billing",
        ]
        return AuditDecision(not problems, checks, problems)

    def _client(self, result: ToolResult) -> AuditDecision:
        rows = self.reader.audit_client_components(result.data["client_key"])
        net = sum(float(row["billed_amount"]) for row in rows)
        profit = sum(float(row["octopus_profit"]) for row in rows)
        expected = {
            "validated_billing": net,
            "octopus_profit": profit,
            "profitability_pct": profit / net * 100 if net else None,
            "valid_operations": len(rows),
            "last_operation": max((row["operation_date"] for row in rows), default=None),
            "months": sorted({row["month"] for row in rows}),
            "channels": sorted({row["channel"] for row in rows}),
        }
        problems = self._compare(result.data, expected)
        expected_evidence = {
            f"operation:{row['operation_key']}|drive:{row['source_drive_id']}" for row in rows
        }
        if set(result.evidence) != expected_evidence:
            problems.append("client evidence does not match valid operations")
        return AuditDecision(
            not problems,
            ["client totals recomputed from valid operations", "excluded states ignored"],
            problems,
        )

    def _reviews(self, limit: int, result: ToolResult) -> AuditDecision:
        problems = []
        cases = result.data.get("cases", [])
        expected = self.reader.audit_review_components(limit)
        if result.data.get("count") != len(cases):
            problems.append("review count differs from returned cases")
        if cases != expected:
            problems.append("review cases differ from the database")
        if any(not case.get("operation_key") or not case.get("source_drive_id") for case in cases):
            problems.append("a review case lacks operation or source identity")
        expected_evidence = {
            f"operation:{row['operation_key']}|drive:{row['source_drive_id']}" for row in expected
        }
        if set(result.evidence) != expected_evidence:
            problems.append("review evidence differs from the database")
        return AuditDecision(not problems, ["every review has documentary identity"], problems)

    @staticmethod
    def _compare(actual: dict, expected: dict) -> list[str]:
        problems = []
        for field, expected_value in expected.items():
            actual_value = actual.get(field)
            if expected_value is None:
                if actual_value is not None:
                    problems.append(f"{field}: expected no value, got {actual_value}")
            elif isinstance(expected_value, float):
                if actual_value is None or not math.isclose(
                    float(actual_value), expected_value, rel_tol=0, abs_tol=0.000001
                ):
                    problems.append(f"{field}: {actual_value} != {expected_value}")
            elif actual_value != expected_value:
                problems.append(f"{field}: {actual_value} != {expected_value}")
        return problems
