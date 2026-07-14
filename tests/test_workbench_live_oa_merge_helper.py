from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_live_oa_merge_helper import WorkbenchLiveOaMergeHelper


class WorkbenchLiveOaMergeHelperTests(unittest.TestCase):
    def test_merge_rows_replaces_oa_rows_and_keeps_only_oa_attachment_invoices(self) -> None:
        helper = WorkbenchLiveOaMergeHelper(serialize_value=lambda value: value)
        live_payload = {
            "paired": {
                "oa": [{"id": "live-oa"}],
                "invoice": [{"id": "invoice-live", "source_kind": "manual"}],
            },
            "unpaired": {
                "oa": [],
                "invoice": [{"id": "invoice-shared", "stale": True}],
            },
        }
        oa_payload = {
            "oa_status": {"code": "ready"},
            "paired": {
                "oa": [{"id": "oa-paired"}],
                "invoice": [
                    {"id": "invoice-oa", "source_kind": "oa_attachment_invoice"},
                    {"id": "invoice-ignored", "source_kind": "manual"},
                ],
            },
            "unpaired": {
                "oa": [{"id": "oa-open"}],
                "invoice": [
                    {"id": "invoice-shared", "source_kind": "oa_attachment_invoice", "fresh": True},
                ],
            },
        }

        merged = helper.merge_rows(live_payload, oa_payload)

        self.assertEqual(merged["paired"]["oa"], [{"id": "oa-paired"}])
        self.assertEqual(merged["unpaired"]["oa"], [{"id": "oa-open"}])
        self.assertEqual(
            merged["paired"]["invoice"],
            [
                {"id": "invoice-live", "source_kind": "manual"},
                {"id": "invoice-oa", "source_kind": "oa_attachment_invoice"},
            ],
        )
        self.assertEqual(
            merged["unpaired"]["invoice"],
            [{"id": "invoice-shared", "source_kind": "oa_attachment_invoice", "fresh": True}],
        )
        self.assertEqual(merged["oa_status"], {"code": "ready"})

    def test_merge_rows_uses_ready_status_default(self) -> None:
        helper = WorkbenchLiveOaMergeHelper(serialize_value=lambda value: value)

        merged = helper.merge_rows({"paired": {}, "unpaired": {}}, {"paired": {}, "unpaired": {}})

        self.assertEqual(merged["oa_status"], {"code": "ready", "message": "OA 已同步"})

    def test_dedupe_rows_by_id_preferring_last_preserves_order_and_passthrough(self) -> None:
        rows = [
            {"id": "a", "version": 1},
            "passthrough",
            {"id": "b", "version": 1},
            {"id": "a", "version": 2},
            {"id": "", "empty": True},
        ]

        self.assertEqual(
            WorkbenchLiveOaMergeHelper.dedupe_rows_by_id_preferring_last(rows),
            [
                {"id": "a", "version": 2},
                {"id": "b", "version": 1},
                "passthrough",
                {"id": "", "empty": True},
            ],
        )


if __name__ == "__main__":
    unittest.main()
