from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import date
from pathlib import Path

from jarvis.agents.auditor import OctopusAuditor
from jarvis.agents.specialist import OctopusSpecialist
from jarvis.core.audit_log import AuditLog
from jarvis.core.contracts import PolicyDenied
from jarvis.core.coordinator import JarvisCoordinator
from jarvis.core.policy import PermissionPolicy
from jarvis.scripts.build_test_db import build_test_database
from jarvis.scripts.create_shadow_snapshot import create_shadow_snapshot, sha256_file
from jarvis.scripts.shadow_observe import observe_shadow, verify_shadow_manifest
from jarvis.scripts.shadow_cycle import run_shadow_cycle
from jarvis.scripts.shadow_reconcile import reconcile_months
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

    def test_shadow_snapshot_does_not_modify_source(self) -> None:
        shadow = Path(self.temp.name) / "octopus_shadow.db"
        source_hash = sha256_file(self.db)
        result = create_shadow_snapshot(self.db, shadow)
        self.assertEqual(sha256_file(self.db), source_hash)
        self.assertTrue(result["source_unchanged"])
        self.assertEqual(result["integrity_check"], "ok")
        self.assertEqual(result["counts"]["rentability_operations"], 4)
        self.assertNotEqual(shadow.resolve(), self.db.resolve())

    def test_shadow_reader_requires_an_isolated_shadow_database(self) -> None:
        shadow = Path(self.temp.name) / "octopus_shadow.db"
        create_shadow_snapshot(self.db, shadow)
        reader = OctopusReader(shadow, environment="shadow", as_of=date(2026, 10, 6))
        self.assertEqual(reader.month_summary("2026-09").data["valid_operations"], 2)
        with self.assertRaisesRegex(ValueError, "SHADOW"):
            OctopusReader(self.db, environment="shadow")

    def test_shadow_policy_can_only_run_read_only_flow(self) -> None:
        shadow = Path(self.temp.name) / "octopus_shadow.db"
        create_shadow_snapshot(self.db, shadow)
        policy_path = Path(__file__).resolve().parents[1] / "config" / "permissions.shadow.json"
        policy = PermissionPolicy(policy_path)
        coordinator = JarvisCoordinator(
            OctopusReader(shadow, environment="shadow", as_of=date(2026, 10, 6)),
            policy,
            AuditLog(Path(self.temp.name) / "shadow_audit.db"),
        )
        response = coordinator.handle("Resumen de septiembre 2026")
        self.assertEqual(response.status, "APPROVED")
        with self.assertRaises(PolicyDenied):
            policy.require_tool("octopus-specialist", "render.deploy")

    def test_shadow_reconciles_with_current_octopus_metrics(self) -> None:
        shadow = Path(self.temp.name) / "octopus_shadow.db"
        create_shadow_snapshot(self.db, shadow)
        report = reconcile_months(shadow, date(2026, 10, 6), ["2026-09", "2026-10"])
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["months_checked"], 2)

    def test_shadow_observation_audits_every_month_and_client(self) -> None:
        shadow = Path(self.temp.name) / "octopus_shadow.db"
        manifest = Path(self.temp.name) / "octopus_shadow_manifest.json"
        create_shadow_snapshot(self.db, shadow, manifest)
        policy_path = Path(__file__).resolve().parents[1] / "config" / "permissions.shadow.json"
        report = observe_shadow(
            shadow,
            manifest,
            policy_path,
            Path(self.temp.name) / "shadow_observation_audit.db",
            date(2026, 10, 6),
        )
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["observations"]["months_total"], 2)
        self.assertEqual(report["observations"]["clients_total"], 2)
        self.assertEqual(report["observations"]["valid_operations_observed"], 2)
        self.assertEqual(report["external_actions_executed"], 0)

    def test_tampered_shadow_snapshot_is_blocked(self) -> None:
        shadow = Path(self.temp.name) / "octopus_shadow.db"
        manifest = Path(self.temp.name) / "octopus_shadow_manifest.json"
        create_shadow_snapshot(self.db, shadow, manifest)
        with shadow.open("ab") as output:
            output.write(b"tampered")
        verification = verify_shadow_manifest(shadow, manifest)
        self.assertFalse(verification["approved"])
        self.assertTrue(any("snapshot hash" in problem for problem in verification["problems"]))

    def test_repeated_shadow_cycle_reports_only_real_drift(self) -> None:
        root = Path(self.temp.name)
        shadow = root / "octopus_shadow.db"
        manifest = root / "octopus_shadow_manifest.json"
        audit = root / "shadow_cycle_audit.db"
        history = root / "shadow_history.db"
        policy_path = Path(__file__).resolve().parents[1] / "config" / "permissions.shadow.json"
        first = run_shadow_cycle(
            source=self.db,
            db_path=shadow,
            manifest_path=manifest,
            policy_path=policy_path,
            audit_path=audit,
            history_path=history,
            as_of=date(2026, 10, 6),
        )
        self.assertTrue(first["drift"]["baseline"])

        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute(
                "INSERT INTO billing_operations"
                "(client_key,month,net_amount,load_date,period_date) VALUES (?,?,?,?,?)",
                ("ACME", "2026-10", 100_000, "2026-10-06", "2026-10-01"),
            )
            conn.execute(
                "INSERT INTO rentability_operations VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("op-acme-2", "ACME", "Acme", "HYF", "2026-10", "2026-10-06", 100_000, 5_000, "OK", "acme-2.jpg", "drive-acme-2"),
            )

        second = run_shadow_cycle(
            source=self.db,
            db_path=shadow,
            manifest_path=manifest,
            policy_path=policy_path,
            audit_path=audit,
            history_path=history,
            as_of=date(2026, 10, 6),
        )
        self.assertFalse(second["drift"]["baseline"])
        self.assertEqual(second["drift"]["affected_months"], ["2026-10"])
        self.assertEqual(second["drift"]["affected_clients"], ["ACME"])
        self.assertEqual(second["drift"]["table_deltas"]["billing_operations"], 1)
        self.assertEqual(second["drift"]["table_deltas"]["rentability_operations"], 1)
        self.assertEqual(second["external_actions_executed"], 0)
        with closing(sqlite3.connect(history)) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM shadow_cycles").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
