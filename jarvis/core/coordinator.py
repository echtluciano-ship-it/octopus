from __future__ import annotations

import uuid
from dataclasses import asdict

from jarvis.agents.auditor import OctopusAuditor
from jarvis.agents.specialist import OctopusSpecialist
from jarvis.core.audit_log import AuditLog
from jarvis.core.contracts import AuditDecision, JarvisResponse, NeedsReview, PlannedAction, ToolResult
from jarvis.core.policy import PermissionPolicy
from jarvis.tools.octopus_reader import OctopusReader


class JarvisCoordinator:
    agent_id = "coordinator"

    def __init__(self, reader: OctopusReader, policy: PermissionPolicy, audit_log: AuditLog) -> None:
        if policy.environment != "test":
            raise ValueError("JARVIS v0 can run only with the TEST policy")
        self.reader = reader
        self.policy = policy
        self.audit_log = audit_log
        self.specialist = OctopusSpecialist()
        self.auditor = OctopusAuditor(reader)

    def handle(self, request: str) -> JarvisResponse:
        run_id = str(uuid.uuid4())
        sequence = 1
        intent = "unclassified"
        self.audit_log.event(run_id, sequence, self.agent_id, "request_received", {"request": request})
        try:
            self.policy.require_agent(self.agent_id, self.specialist.agent_id)
            action = self.specialist.plan(request)
            intent = action.intent
            sequence += 1
            self.audit_log.event(run_id, sequence, self.specialist.agent_id, "action_planned", asdict(action))

            self.policy.require_tool(self.specialist.agent_id, action.tool)
            result = self._execute(action)
            sequence += 1
            self.audit_log.event(
                run_id,
                sequence,
                self.specialist.agent_id,
                "tool_completed",
                {"tool": result.tool, "data": result.data, "evidence": result.evidence},
            )

            self.policy.require_agent(self.agent_id, self.auditor.agent_id)
            audit_tool = {
                "month_summary": "octopus.audit_month_components",
                "client_snapshot": "octopus.audit_client_components",
                "review_cases": "octopus.audit_review_components",
            }.get(action.intent)
            if audit_tool:
                self.policy.require_tool(self.auditor.agent_id, audit_tool)
            decision = self.auditor.verify(action, result)
            sequence += 1
            self.audit_log.event(run_id, sequence, self.auditor.agent_id, "audit_completed", asdict(decision))
            if not decision.approved:
                answer = "REVIEW: el auditor detecto diferencias y el resultado no fue publicado."
                status = "REVIEW"
            else:
                answer = self._render(action, result)
                status = "APPROVED"
            response = JarvisResponse(run_id, status, answer, result.evidence, decision)
        except Exception as exc:
            decision = AuditDecision(False, [], [str(exc)])
            response = JarvisResponse(
                run_id,
                "REVIEW",
                f"REVIEW: {exc}",
                [],
                decision,
            )
            sequence += 1
            self.audit_log.event(run_id, sequence, self.agent_id, "controlled_failure", {"error": str(exc)})

        self.audit_log.complete(
            run_id=run_id,
            request=request,
            intent=intent,
            status=response.status,
            response=response.answer,
            audit=asdict(response.audit),
        )
        return response

    def _execute(self, action: PlannedAction) -> ToolResult:
        if action.tool == "octopus.month_summary":
            return self.reader.month_summary(**action.arguments)
        if action.tool == "octopus.client_snapshot":
            return self.reader.client_snapshot(**action.arguments)
        if action.tool == "octopus.review_cases":
            return self.reader.review_cases(**action.arguments)
        raise NeedsReview(f"No executor registered for {action.tool}")

    @staticmethod
    def _money(value: float) -> str:
        return "$" + f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def _render(self, action: PlannedAction, result: ToolResult) -> str:
        data = result.data
        if action.intent == "month_summary":
            pct = "Sin datos" if data["profitability_pct"] is None else f"{data['profitability_pct']:.2f}%"
            return (
                f"Resumen {data['month']}\n"
                f"Facturacion total: {self._money(data['billing_total'])}\n"
                f"Facturacion validada: {self._money(data['validated_billing'])}\n"
                f"Ganancia Octopus: {self._money(data['octopus_profit'])}\n"
                f"Rentabilidad global: {pct}\n"
                f"Operaciones validas: {data['valid_operations']}"
            )
        if action.intent == "client_snapshot":
            pct = "Sin datos" if data["profitability_pct"] is None else f"{data['profitability_pct']:.2f}%"
            return (
                f"Cliente: {data['display_name']}\n"
                f"Facturacion validada: {self._money(data['validated_billing'])}\n"
                f"Ganancia Octopus: {self._money(data['octopus_profit'])}\n"
                f"Rentabilidad: {pct}\n"
                f"Ultima operacion: {data['last_operation']}\n"
                f"Canales: {', '.join(data['channels'])}"
            )
        if action.intent == "review_cases":
            if not data["cases"]:
                return "No hay casos en REVIEW."
            lines = [f"Casos en REVIEW: {data['count']}"]
            lines.extend(
                f"- {case['client_name']} | {case['channel']} | {case['month']} | {case['source_file']}"
                for case in data["cases"]
            )
            return "\n".join(lines)
        raise NeedsReview(f"No renderer registered for {action.intent}")
