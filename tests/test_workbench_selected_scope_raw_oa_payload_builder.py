from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_selected_scope_raw_oa_payload_builder import (
    WorkbenchSelectedScopeRawOaPayloadBuilder,
)


class WorkbenchSelectedScopeRawOaPayloadBuilderTests(unittest.TestCase):
    def test_build_includes_month_rows_and_retained_attachment_invoices(self) -> None:
        snapshots = [
            {
                "id": "oa-month",
                "type": "oa",
                "_month": "2026-03",
                "_section": "paired",
                "oa_bank_relation": {"tone": "danger"},
            },
            {
                "id": "oa-retained",
                "type": "oa",
                "_month": "2025-12",
                "_section": "unpaired",
                "oa_bank_relation": {"tone": "warn"},
            },
            {
                "id": "invoice-retained",
                "type": "invoice",
                "_month": "2025-12",
                "_section": "unpaired",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-retained",
                "invoice_bank_relation": {"tone": "danger"},
            },
            {
                "id": "invoice-ignored",
                "type": "invoice",
                "_month": "2025-12",
                "_section": "unpaired",
                "source_kind": "manual",
                "derived_from_oa_id": "oa-retained",
            },
        ]
        builder = WorkbenchSelectedScopeRawOaPayloadBuilder(
            manual_retained_oa_row_ids=lambda: ["oa-retained"],
            record_snapshots=lambda: snapshots,
            serialize_row=lambda row: {**row, "serialized": True},
            oa_status_payload=lambda: {"ready": True},
        )

        payload = builder.build(months={"2026-03"}, supplemental_oa_row_ids=set())

        self.assertEqual([row["id"] for row in payload["paired"]["oa"]], ["oa-month"])
        self.assertEqual([row["id"] for row in payload["unpaired"]["oa"]], ["oa-retained"])
        self.assertEqual([row["id"] for row in payload["unpaired"]["invoice"]], ["invoice-retained"])
        self.assertEqual(payload["oa_status"], {"ready": True})
        self.assertEqual(payload["summary"]["oa_count"], 2)
        self.assertEqual(payload["summary"]["invoice_count"], 1)
        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["unpaired_count"], 2)
        self.assertEqual(payload["summary"]["exception_count"], 2)
        self.assertTrue(payload["unpaired"]["oa"][0]["serialized"])

    def test_build_includes_supplemental_retained_oa_rows(self) -> None:
        builder = WorkbenchSelectedScopeRawOaPayloadBuilder(
            manual_retained_oa_row_ids=lambda: [],
            record_snapshots=lambda: [
                {
                    "id": "oa-linked-bank",
                    "type": "oa",
                    "_month": "2025-11",
                    "_section": "unpaired",
                },
            ],
            serialize_row=lambda row: row,
            oa_status_payload=lambda: {},
        )

        payload = builder.build(months={"2026-03"}, supplemental_oa_row_ids={"oa-linked-bank"})

        self.assertEqual([row["id"] for row in payload["unpaired"]["oa"]], ["oa-linked-bank"])
        self.assertEqual(payload["summary"]["oa_count"], 1)

    def test_build_uses_record_snapshot_once(self) -> None:
        calls: list[str] = []
        snapshots = [
            {"id": "oa-1", "type": "oa", "_month": "2026-01", "_section": "unpaired"},
            {"id": "oa-2", "type": "oa", "_month": "2026-01", "_section": "unpaired"},
        ]

        def record_snapshots() -> list[dict[str, object]]:
            calls.append("snapshots")
            return snapshots

        builder = WorkbenchSelectedScopeRawOaPayloadBuilder(
            manual_retained_oa_row_ids=lambda: [],
            record_snapshots=record_snapshots,
            serialize_row=lambda row: row,
            oa_status_payload=lambda: {},
        )

        payload = builder.build(months={"2026-01"}, supplemental_oa_row_ids=set())

        self.assertEqual(calls, ["snapshots"])
        self.assertEqual({row["id"] for row in payload["unpaired"]["oa"]}, {"oa-1", "oa-2"})


if __name__ == "__main__":
    unittest.main()
