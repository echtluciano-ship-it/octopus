from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import data_loader
import metrics
from data_access import clear_cache, read_sql
from sync_checks import reconcile_database, verify_manifest, write_manifest, SOURCE_FILES


AS_OF = date(2026, 9, 18)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "octopus.db"
        self.conn = sqlite3.connect(self.path)
        data_loader.reset_schema(self.conn)
        self.bill("A", "Cliente A", "2026-09", "2026-09-18", 1000)
        self.bill("A", "Cliente A SA", "2026-09", "2026-09-18", 2000)
        self.bill("B", "Cliente B", "2026-09", "2026-09-19", 9000)
        self.bill("A", "Cliente A", "2026-08", "2026-09-01", 100)
        self.rent("one", "A", "Cliente A", 100, 20)
        self.rent("two", "A", "Cliente A SA", 300, 15)
        self.rent("future", "B", "Cliente B", 9999, 999, day="2026-09-19")
        self.rent("transfer", "B", "Cliente B", 100, 1.2, status="OK_TRANSFERENCIA_1_2")
        for state in ("REVISION", "DUPLICADO", "EXCLUIDO", "NO_PROCESAR"):
            self.rent(state, "A", "Cliente A", 5000, 500, status=state)
        self.rent("missing_net", "A", "Cliente A", None, 500)
        self.rent("missing_profit", "A", "Cliente A", 5000, None)
        self.rebuild()
        clear_cache()

    def tearDown(self):
        self.conn.close()
        clear_cache()
        self.temp.cleanup()

    def bill(self, key, name, month, day, amount):
        self.conn.execute("""INSERT INTO billing_operations
            (client_key,client_name,channel,month,period_date,load_date,net_amount,source)
            VALUES (?,?,'HYF',?,?,?,?,'fixture')""", (key,name,month,month+'-01',day,amount))

    def rent(self, key, client, name, net, profit, status="OK", day="2026-09-18"):
        self.conn.execute("""INSERT INTO rentability_operations
            (operation_key,client_key,client_name,channel,month,operation_date,billed_amount,octopus_profit,status)
            VALUES (?,?,?,'HYF',?,?,?,?,?)""", (key,client,name,day[:7],day,net,profit,status))

    def rebuild(self):
        self.conn.execute("DELETE FROM clients")
        data_loader.rebuild_clients(self.conn)
        data_loader.rebuild_monthly_metrics(self.conn)
        self.conn.commit()

    def read(self, query, params=()):
        return read_sql(query, params, self.path)

    def test_weighted_ranking_canonical_names_cutoff_and_exclusions(self):
        billing, rent = metrics.executive_summary("2026-09", AS_OF, self.read)
        ranking = metrics.rentability_ranking("2026-09", 20, AS_OF, self.read)
        self.assertEqual(billing.iloc[0].facturacion, 3000)
        self.assertEqual(rent.iloc[0].operaciones, 3)
        self.assertEqual(rent.iloc[0].facturacion_neta_rentabilidad, 500)
        self.assertAlmostEqual(rent.iloc[0].ganancia_octopus, 36.2)
        self.assertEqual(len(ranking), 2)
        self.assertAlmostEqual(ranking.iloc[0].rentabilidad, 35 / 400)
        for limit in (5, 10, 20):
            pd.testing.assert_frame_equal(metrics.rentability_ranking("2026-09", limit, AS_OF, self.read), ranking)
        august, _ = metrics.executive_summary("2026-08", AS_OF, self.read)
        self.assertEqual(august.iloc[0].facturacion, 100)
        future_b, future_r = metrics.executive_summary("2026-10", AS_OF, self.read)
        self.assertEqual(future_b.iloc[0].registros, 0)
        self.assertEqual(future_r.iloc[0].operaciones, 0)

    def test_new_card_refreshes_summary_ranking_and_client_cache_without_clearing(self):
        before = metrics.executive_summary("2026-09", AS_OF, self.read)
        metrics.rentability_ranking("2026-09", 20, AS_OF, self.read)
        self.read("SELECT COUNT(*) n FROM clients")
        self.rent("new", "C", "Cliente C", 200, 60)
        self.rebuild()
        after = metrics.executive_summary("2026-09", AS_OF, self.read)
        pd.testing.assert_frame_equal(before[0], after[0])
        self.assertEqual(after[1].iloc[0].operaciones, 4)
        self.assertEqual(after[1].iloc[0].facturacion_neta_rentabilidad, 700)
        self.assertAlmostEqual(after[1].iloc[0].ganancia_octopus, 96.2)
        self.assertEqual(metrics.rentability_ranking("2026-09", 20, AS_OF, self.read).iloc[0].client_key, "C")
        self.assertEqual(self.read("SELECT COUNT(*) n FROM clients").iloc[0].n, 3)
        reconcile_database(self.conn, AS_OF)

    def test_updated_billing_refreshes_its_own_metrics(self):
        metrics.billing_ranking("2026-09", 20, AS_OF, self.read)
        before_rent = metrics.executive_summary("2026-09", AS_OF, self.read)[1]
        self.bill("B", "Cliente B", "2026-09", "2026-09-18", 6000)
        self.rebuild()
        billing, rent = metrics.executive_summary("2026-09", AS_OF, self.read)
        self.assertEqual(billing.iloc[0].facturacion, 9000)
        pd.testing.assert_frame_equal(before_rent, rent)
        self.assertEqual(metrics.billing_ranking("2026-09", 20, AS_OF, self.read).iloc[0].client_key, "B")

    def test_wal_commits_refresh_same_query(self):
        self.conn.execute("PRAGMA journal_mode=WAL")
        query = "SELECT SUM(net_amount) n FROM billing_operations"
        before = self.read(query).iloc[0].n
        self.bill("A", "Cliente A", "2026-09", "2026-09-18", 55)
        self.conn.commit()
        self.assertEqual(self.read(query).iloc[0].n, before + 55)

    def test_day_rollover_includes_due_records(self):
        old = metrics.executive_summary("2026-09", AS_OF, self.read)[1]
        new = metrics.executive_summary("2026-09", date(2026, 9, 19), self.read)[1]
        self.assertEqual(int(new.iloc[0].operaciones), int(old.iloc[0].operaciones) + 1)

    def test_monthly_table_has_one_row_per_client_channel_month(self):
        report = reconcile_database(self.conn, AS_OF)
        self.assertEqual(report["published_clients"], 2)
        row = self.conn.execute("SELECT rentability_billed,octopus_profit,rentability_operations FROM monthly_metrics WHERE client_key='A' AND month='2026-09'").fetchone()
        self.assertEqual(row, (400, 35, 2))

    def test_scoped_rebuild_matches_full_rebuild_for_affected_data(self):
        partial = sqlite3.connect(":memory:")
        self.conn.backup(partial)
        additions = (
            ("incremental-a", "A", "Cliente A", "2026-09-18", 250, 25),
            ("incremental-c", "C", "Cliente C", "2026-09-18", 600, 90),
        )
        for conn in (self.conn, partial):
            for key, client, name, day, net, profit in additions:
                conn.execute(
                    """INSERT INTO rentability_operations
                    (operation_key,client_key,client_name,channel,month,operation_date,
                     billed_amount,octopus_profit,status)
                    VALUES (?,?,?,'HYF',?,?,?,?, 'OK')""",
                    (key, client, name, day[:7], day, net, profit),
                )

        self.rebuild()
        affected_clients = {"A", "C"}
        affected_metrics = {("A", "HYF", "2026-09"), ("C", "HYF", "2026-09")}
        data_loader.rebuild_clients(partial, affected_clients)
        data_loader.rebuild_monthly_metrics(partial, affected_metrics)
        partial.commit()

        self.assertEqual(
            self.conn.execute("SELECT * FROM clients ORDER BY client_key").fetchall(),
            partial.execute("SELECT * FROM clients ORDER BY client_key").fetchall(),
        )
        metric_columns = (
            "client_key,client_name,channel,month,billing_total,rentability_billed,"
            "octopus_profit,rentability_pct,billing_operations,rentability_operations,has_pending_data"
        )
        self.assertEqual(
            self.conn.execute(f"SELECT {metric_columns} FROM monthly_metrics ORDER BY client_key,channel,month").fetchall(),
            partial.execute(f"SELECT {metric_columns} FROM monthly_metrics ORDER BY client_key,channel,month").fetchall(),
        )
        self.assertEqual(reconcile_database(self.conn, AS_OF), reconcile_database(partial, AS_OF))
        partial.close()

    def test_failed_load_preserves_previous_database(self):
        before = self.path.read_bytes()
        with patch.object(data_loader, "DB_PATH", self.path), patch.object(data_loader, "load_billing", side_effect=ValueError("bad input")):
            with self.assertRaisesRegex(ValueError, "bad input"):
                data_loader.load_database()
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(list(self.path.parent.glob('.octopus-*.db')), [])

    def test_deploy_manifest_rejects_source_change_without_reload(self):
        root = self.path.parent
        for name in SOURCE_FILES:
            target = root / name
            target.parent.mkdir(exist_ok=True)
            target.write_text("fixture", encoding="utf-8")
        write_manifest(root, reconcile_database(self.conn, AS_OF))
        verify_manifest(root)
        (root / SOURCE_FILES[1]).write_text("new card", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "rebuild and reconcile"):
            verify_manifest(root)


if __name__ == "__main__":
    unittest.main()
