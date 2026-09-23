from __future__ import annotations

import unittest

from scripts.drive_delta import build_plan, commit_snapshot
from scripts.incremental_refresh import group_records_by_drive_id, record_groups_changed


class DriveDeltaTests(unittest.TestCase):
    def setUp(self):
        self.known = {
            "drive_id": "known",
            "name": "card.jpg",
            "mime_type": "image/jpeg",
            "size_bytes": 100,
            "modified_time": "2026-09-20T10:00:00Z",
            "folder_id": "folder",
            "folder_period": "2026-09",
            "source_type": "pendientes",
            "url": "https://drive/known",
        }
        self.state = {
            "version": 1,
            "documents": {"known": self.known.copy()},
            "official_sources": {"billing": {"modified_time": "old"}},
        }

    def test_same_metadata_is_unchanged_without_downloading(self):
        plan = build_plan(self.state, {"files": [self.known.copy()]})
        self.assertEqual(plan["counts"], {
            "detected": 1,
            "new": 0,
            "modified": 0,
            "unchanged": 1,
            "official_sources_changed": 0,
        })

    def test_same_drive_id_with_new_metadata_is_modified(self):
        changed = self.known | {"size_bytes": 101, "modified_time": "2026-09-21T10:00:00Z"}
        plan = build_plan(self.state, {"files": [changed]})
        self.assertEqual(plan["counts"]["modified"], 1)
        self.assertEqual(plan["modified"][0]["after"]["drive_id"], "known")

    def test_new_drive_id_is_new_even_when_name_and_size_match(self):
        other = self.known | {"drive_id": "other"}
        plan = build_plan(self.state, {"files": [other]})
        self.assertEqual(plan["counts"]["new"], 1)
        self.assertEqual(plan["counts"]["modified"], 0)

    def test_commit_advances_watermark_and_preserves_known_documents(self):
        snapshot = {
            "scan_started_at": "2026-09-21T12:00:00Z",
            "files": [self.known | {"drive_id": "other"}],
            "official_sources": {"billing": {"modified_time": "new"}},
        }
        committed = commit_snapshot(self.state, snapshot)
        self.assertEqual(committed["last_successful_scan"], snapshot["scan_started_at"])
        self.assertEqual(set(committed["documents"]), {"known", "other"})
        self.assertEqual(committed["official_sources"]["billing"]["modified_time"], "new")


class MultiMonthOperationTests(unittest.TestCase):
    def operation(self, month: str, billed: float, profit: float) -> dict:
        record = {
            "operation_key": f"split-{month}",
            "client_key": "HASAR",
            "client_name": "Hasar",
            "original_client_name": "Hasar",
            "channel": "HYF",
            "operation_date": f"{month}-25",
            "month": month,
            "check_amount": None,
            "net_billing_amount": billed,
            "billed_amount": billed,
            "octopus_profit": profit,
            "status": "OK_MULTI_MONTH_SPLIT",
            "operation_type": "MULTI_MONTH_SPLIT",
            "source_file": "card.jpg",
            "source_path": "card.jpg#drive_id_same",
            "reference": month,
            "note": "fixture",
            "source_drive_id": "same",
        }
        return record

    def test_one_document_can_create_two_monthly_fragments(self) -> None:
        records = [
            self.operation("2026-09", 90, 9),
            self.operation("2026-10", 10, 1),
        ]
        grouped = group_records_by_drive_id(records)

        self.assertEqual(list(grouped), ["same"])
        self.assertEqual(len(grouped["same"]), 2)
        self.assertFalse(record_groups_changed(records, [dict(row) for row in reversed(records)]))

    def test_changed_fragment_is_detected_without_collapsing_document(self) -> None:
        existing = [
            self.operation("2026-09", 90, 9),
            self.operation("2026-10", 10, 1),
        ]
        current = [dict(existing[0]), dict(existing[1], billed_amount=11)]

        self.assertTrue(record_groups_changed(current, existing))


if __name__ == "__main__":
    unittest.main()
