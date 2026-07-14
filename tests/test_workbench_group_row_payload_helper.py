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
        rows_by_id: dict[str, dict[str, object]],
        active_relations: list[dict[str, object]],
    ) -> dict[str, object]:
        self.calls.append(
            {
                "month": month,
                "rows_by_id": rows_by_id,
                "active_relations": active_relations,
            }
        )
        return {"month": month, "paired": {"groups": []}, "unpaired": {"groups": []}}


class WorkbenchGroupRowPayloadHelperTests(unittest.TestCase):
    def test_group_filters_ignored_rows_and_passes_only_formal_relations(self) -> None:
        grouping_service = FakeGroupingService()
        helper = WorkbenchGroupRowPayloadHelper(
            grouping_service=grouping_service,
            serialize_value=lambda value: {**value, "serialized": True} if isinstance(value, dict) else value,
        )
        payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready"},
            "paired": {
                "oa": [
                    {"id": "oa-1", "type": "oa", "case_id": "CASE-1"},
                    {"id": "oa-ignored", "type": "oa", "case_id": "CASE-1", "ignored": True},
                ],
                "bank": [{"id": "bank-1", "type": "bank", "case_id": "CASE-1"}],
                "invoice": [{"id": "invoice-1", "type": "invoice", "case_id": "CASE-1"}],
            },
            "unpaired": {
                "oa": [{"id": "oa-2", "type": "oa"}],
                "bank": [{"id": "bank-ignored", "type": "bank", "ignored": True}],
                "invoice": [{"id": "invoice-2", "type": "invoice"}],
            },
        }

        grouped = helper.group(payload)

        self.assertEqual(grouping_service.calls[0]["month"], "2026-03")
        self.assertEqual(set(grouping_service.calls[0]["rows_by_id"]), {"oa-1", "oa-2", "bank-1", "invoice-1", "invoice-2"})
        self.assertEqual(
            grouping_service.calls[0]["active_relations"],
            [
                {
                    "case_id": "CASE-1",
                    "row_ids": ["oa-1", "bank-1", "invoice-1"],
                    "row_types": ["oa", "bank", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                }
            ],
        )
        self.assertEqual(grouped["oa_status"], {"code": "ready", "serialized": True})

    def test_group_tolerates_missing_sections(self) -> None:
        grouping_service = FakeGroupingService()
        helper = WorkbenchGroupRowPayloadHelper(
            grouping_service=grouping_service,
            serialize_value=lambda value: value,
        )

        grouped = helper.group({"month": "all", "paired": None, "unpaired": None})

        self.assertEqual(grouped["month"], "all")
        self.assertEqual(grouping_service.calls[0]["rows_by_id"], {})
        self.assertEqual(grouping_service.calls[0]["active_relations"], [])


if __name__ == "__main__":
    unittest.main()
