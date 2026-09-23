from __future__ import annotations

import sqlite3
import unittest
from datetime import date

from data_loader import make_operation_key


class OperationIdentityTests(unittest.TestCase):
    def test_same_client_and_date_can_store_distinct_drive_operations(self) -> None:
        common = (date(2026, 9, 17), "MEDICAID", "HYF", 3_232_177.0, 285_306.0)
        first_key = make_operation_key("card.jpg#drive_id_first", *common)
        second_key = make_operation_key("card.jpg#drive_id_second", *common)
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE operations (operation_key TEXT PRIMARY KEY)")

        conn.execute("INSERT INTO operations VALUES (?)", (first_key,))
        conn.execute("INSERT INTO operations VALUES (?)", (second_key,))

        self.assertNotEqual(first_key, second_key)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0], 2)

    def test_one_drive_document_can_have_distinct_month_fragments(self) -> None:
        common = (date(2026, 9, 25), "HASAR", "HYF", 100.0, 10.0)
        september = make_operation_key("card.jpg#drive_id_same", *common, "2026-09")
        october = make_operation_key("card.jpg#drive_id_same", *common, "2026-10")

        self.assertEqual(september, "drive:same:fragment:2026-09")
        self.assertEqual(october, "drive:same:fragment:2026-10")
        self.assertNotEqual(september, october)


if __name__ == "__main__":
    unittest.main()
