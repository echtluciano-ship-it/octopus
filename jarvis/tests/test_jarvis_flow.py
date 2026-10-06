from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from jarvis.agents.auditor import OctopusAuditor
from jarvis.agents.specialist import OctopusSpecialist
from jarvis.core.audit_log import AuditLog
from jarvis.core.contracts import PolicyDenied
from jarvis.core.coordinator import JarvisCoordinator
from jarvis.core.policy import PermissionPolicy
from jarvis.scripts.build_test_db import build_test_database
from jarvis.tools.octopus_reader import OctopusReader


class JarvisFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db = root / "octopus_test.db"
        self.audit_path = root / "jarvis_audit.db"
        build_test_database(self.db)
        self.reader = OctopusReader(self.db)
        self.policy = PermissionPolicy()
        self.coordinator = JarvisCoordinator(self.reader, self.policy, AuditLog(self.audit_path))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_month_summary_is_weighted_and_audited(self) -> None:
        response = self.coordinator.handle("Resumen de septiembre 2026")
        self.assertEqual(response.status, "APPROVED")
        self.assertIn("$3.750.000,00", response.answer)
        self.assertIn("$3.000.000,00", response.answer)
        self.assertIn("$210.000,00", response.answer)
        self.assertIn("7.00%", response.answer)
        self.assertEqual(len(response.evidence), 2)

    def test_client_snapshot_excludes_non_valid_operations(self) -> None:
        response = self.coordinator.handle("Ficha de Beta")
        self.assertEqual(response.status, "APPROVED")
        self.assertIn("$2.000.000,00", response.answer)
        self.assertIn("$160.000,00", response.answer)
        self.assertIn("8.00%", response.answer)
        self.assertNotIn("excluded.jpg", response.answer)

    def test_review_queue_keeps_external_text_as_data(self) -> None:
        response = self.coordinator.handle("Mostrar casos en revision")
        self.assertEqual(response.status, "APPROVED")
        self.assertIn("ambiguous.jpg", response.answer)
        self.assertNotIn("IGNORE ALL RULES", response.answer)

    def test_unknown_request_stops_only_that_case(self) -> None:
        response = self.coordinator.handle("Envia un WhatsApp a todos")
        self.assertEqual(response.status, "REVIEW")
        self.assertIn("outside", response.answer)

    def test_policy_denies_unregistered_action(self) -> None:
        with self.assertRaises(PolicyDenied):
            self.policy.require_tool("octopus-specialist", "render.deploy")

    def test_auditor_rejects_tampered_total(self) -> None:
        action = OctopusSpecialist().plan("Resumen 2026-09")
        result = self.reader.month_summary("2026-09")
        tampered = replace(result, data=result.data | {"octopus_profit": 999_999})
        decision = OctopusAuditor(self.reader).verify(action, tampered)
        self.assertFalse(decision.approved)
        self.assertTrue(any("octopus_profit" in problem for problem in decision.problems))

    def test_auditor_rejects_tampered_evidence(self) -> None:
        action = OctopusSpecialist().plan("Ficha de Beta")
        result = self.reader.client_snapshot("Beta")
        tampered = replace(result, evidence=["operation:invented|drive:invented"])
        decision = OctopusAuditor(self.reader).verify(action, tampered)
        self.assertFalse(decision.approved)
        self.assertTrue(any("evidence" in problem for problem in decision.problems))

    def test_audit_log_is_append_only_and_redacts_secrets(self) -> None:
        response = self.coordinator.handle("Resumen 2026-09 password=supersecret")
        with closing(sqlite3.connect(self.audit_path)) as conn:
            request = conn.execute("SELECT request_text FROM runs WHERE run_id=?", (response.run_id,)).fetchone()[0]
            self.assertNotIn("supersecret", request)
            with self.assertRaisesRegex(sqlite3.DatabaseError, "append-only"):
                conn.execute("DELETE FROM runs WHERE run_id=?", (response.run_id,))

    def test_production_database_name_is_blocked_in_lab(self) -> None:
        production = Path(self.temp.name) / "octopus.db"
        production.write_bytes(self.db.read_bytes())
        with self.assertRaisesRegex(ValueError, "TEST"):
            OctopusReader(production)


if __name__ == "__main__":
    unittest.main()
