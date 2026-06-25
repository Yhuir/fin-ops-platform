from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_group_row_payload_helper import WorkbenchGroupRowPayloadHelper


class FakeGroupingService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def group_payload(
        self,
        month: str,
        *,
        oa_rows: list[dict[str, object]],
        bank_rows: list[dict[str, object]],
        invoice_rows: list[dict[str, object]],
        turnover_relations: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "month": month,
                "oa_rows": oa_rows,
                "bank_rows": bank_rows,
                "invoice_rows": invoice_rows,
                "turnover_relations": turnover_relations,
            }
        )
        return {"month": month, "paired": {"groups": []}, "open": {"groups": []}}


class WorkbenchGroupRowPayloadHelperTests(unittest.TestCase):
    def test_group_filters_ignored_rows_and_passes_turnover_relations(self) -> None:
        grouping_service = FakeGroupingService()
        helper = WorkbenchGroupRowPayloadHelper(
            grouping_service=grouping_service,
            serialize_value=lambda value: {**value, "serialized": True} if isinstance(value, dict) else value,
        )
        payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready"},
            "paired": {
                "oa": [{"id": "oa-1"}, {"id": "oa-ignored", "ignored": True}],
                "bank": [{"id": "bank-1"}],
                "invoice": [{"id": "invoice-1"}],
            },
            "open": {
                "oa": [{"id": "oa-2"}],
                "bank": [{"id": "bank-ignored", "ignored": True}],
                "invoice": [{"id": "invoice-2"}],
            },
        }
        turnover_relations = [{"id": "turnover-1"}]

        grouped = helper.group(payload, turnover_relations=turnover_relations)

        self.assertEqual(grouping_service.calls[0]["month"], "2026-03")
        self.assertEqual(grouping_service.calls[0]["oa_rows"], [{"id": "oa-1"}, {"id": "oa-2"}])
        self.assertEqual(grouping_service.calls[0]["bank_rows"], [{"id": "bank-1"}])
        self.assertEqual(grouping_service.calls[0]["invoice_rows"], [{"id": "invoice-1"}, {"id": "invoice-2"}])
        self.assertEqual(grouping_service.calls[0]["turnover_relations"], turnover_relations)
        self.assertEqual(grouped["oa_status"], {"code": "ready", "serialized": True})

    def test_group_tolerates_missing_sections(self) -> None:
        grouping_service = FakeGroupingService()
        helper = WorkbenchGroupRowPayloadHelper(
            grouping_service=grouping_service,
            serialize_value=lambda value: value,
        )

        grouped = helper.group({"month": "all", "paired": None, "open": None})

        self.assertEqual(grouped["month"], "all")
        self.assertEqual(grouping_service.calls[0]["oa_rows"], [])
        self.assertEqual(grouping_service.calls[0]["bank_rows"], [])
        self.assertEqual(grouping_service.calls[0]["invoice_rows"], [])


if __name__ == "__main__":
    unittest.main()
