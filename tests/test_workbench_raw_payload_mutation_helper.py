from __future__ import annotations

import unittest
from datetime import datetime

from fin_ops_platform.services.workbench_raw_payload_mutation_helper import WorkbenchRawPayloadMutationHelper


class WorkbenchRawPayloadMutationHelperTests(unittest.TestCase):
    def test_replace_row_serializes_replacement_in_all_sections(self) -> None:
        payload: dict[str, object] = {
            "paired": {"invoice": [{"id": "invoice-1", "old": True}]},
            "unpaired": {"invoice": [{"id": "invoice-1", "old": True}]},
        }
        helper = WorkbenchRawPayloadMutationHelper(
            serialize_value=lambda value: {**value, "serialized": True} if isinstance(value, dict) else value,
        )

        replaced = helper.replace_row(
            payload,
            row_type="invoice",
            replacement={"id": "invoice-1", "updated_at": datetime(2026, 1, 1)},
        )

        self.assertTrue(replaced)
        self.assertEqual(payload["paired"]["invoice"][0]["serialized"], True)
        self.assertEqual(payload["unpaired"]["invoice"][0]["serialized"], True)

    def test_replace_row_returns_false_without_matching_or_valid_id(self) -> None:
        helper = WorkbenchRawPayloadMutationHelper(serialize_value=lambda value: value)

        self.assertFalse(helper.replace_row({"paired": {"invoice": []}}, row_type="invoice", replacement={}))
        self.assertFalse(
            helper.replace_row(
                {"paired": {"invoice": [{"id": "other"}]}, "unpaired": {"invoice": []}},
                row_type="invoice",
                replacement={"id": "invoice-1"},
            )
        )

    def test_dedupe_rows_by_id_keeps_first_seen_and_passthrough_rows(self) -> None:
        payload: dict[str, object] = {
            "paired": {"invoice": [{"id": "invoice-1"}, {"id": "invoice-2"}]},
            "unpaired": {"invoice": [{"id": "invoice-1", "duplicate": True}, "passthrough", {"id": ""}]},
        }

        WorkbenchRawPayloadMutationHelper.dedupe_rows_by_id(payload, row_type="invoice")

        self.assertEqual(payload["paired"]["invoice"], [{"id": "invoice-1"}, {"id": "invoice-2"}])
        self.assertEqual(payload["unpaired"]["invoice"], ["passthrough", {"id": ""}])

    def test_refresh_summary_counts_rows_and_open_danger_relations(self) -> None:
        payload: dict[str, object] = {
            "paired": {
                "oa": [{"id": "oa-paired"}],
                "bank": [{"id": "bank-paired"}],
                "invoice": [{"id": "invoice-paired"}],
            },
            "unpaired": {
                "oa": [{"id": "oa-open", "oa_bank_relation": {"tone": "danger"}}],
                "bank": [{"id": "bank-open", "invoice_relation": {"tone": "danger"}}],
                "invoice": [{"id": "invoice-open", "invoice_bank_relation": {"tone": "warn"}}],
            },
        }

        WorkbenchRawPayloadMutationHelper.refresh_summary(payload)

        self.assertEqual(
            payload["summary"],
            {
                "oa_count": 2,
                "bank_count": 2,
                "invoice_count": 2,
                "paired_count": 3,
                "unpaired_count": 3,
                "exception_count": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
