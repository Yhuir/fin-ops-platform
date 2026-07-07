from __future__ import annotations

import unittest
from copy import deepcopy

from fin_ops_platform.services.workbench_oa_invoice_offset_desired_relation_builder import (
    WorkbenchOaInvoiceOffsetDesiredRelationBuilder,
)


class WorkbenchOaInvoiceOffsetDesiredRelationBuilderTests(unittest.TestCase):
    def _builder(
        self,
        *,
        applicant_names: list[str] | None = None,
        conflict_row_ids: set[str] | None = None,
        amount_check: dict[str, object] | None = None,
    ) -> WorkbenchOaInvoiceOffsetDesiredRelationBuilder:
        conflicts = conflict_row_ids or set()

        def attachment_rows(oa_row: dict[str, object], invoice_rows: list[dict[str, object]]) -> list[dict[str, object]]:
            oa_id = str(oa_row.get("id") or "").strip()
            return [
                row
                for row in invoice_rows
                if str(row.get("source_kind") or "") == "oa_attachment_invoice"
                and str(row.get("derived_from_oa_id") or "") == oa_id
            ]

        def month_scope(rows: list[dict[str, object]]) -> str:
            months = {str(row.get("month") or "").strip() for row in rows if str(row.get("month") or "").strip()}
            return next(iter(months)) if len(months) == 1 else "all"

        def amount_check_for_rows(rows: dict[str, list[dict[str, object]]]) -> dict[str, object]:
            return amount_check or {
                "status": "matched",
                "row_counts": {key: len(value) for key, value in rows.items()},
            }

        return WorkbenchOaInvoiceOffsetDesiredRelationBuilder(
            applicant_names_provider=lambda: applicant_names if applicant_names is not None else [" 周洁莹 "],
            serialize_value=lambda value: deepcopy(value),
            attachment_invoice_rows_for_oa=attachment_rows,
            auto_pair_conflicts_with_manual_relation=lambda row_ids: bool(set(row_ids).intersection(conflicts)),
            month_scope_for_relation=month_scope,
            amount_check_for_rows_by_type=amount_check_for_rows,
        )

    def test_build_returns_desired_relation_for_configured_applicant_attachment_rows(self) -> None:
        payload = {
            "open": {
                "oa": [{"id": "oa-1", "applicant": "周洁莹", "month": "2026-03"}],
                "invoice": [
                    {
                        "id": "inv-1",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-1",
                        "month": "2026-03",
                    },
                    {
                        "id": "inv-2",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-1",
                        "month": "2026-03",
                    },
                ],
            }
        }

        desired = self._builder().build(payload)

        self.assertEqual(set(desired), {"CASE-OA-OFFSET-oa-1"})
        self.assertEqual(desired["CASE-OA-OFFSET-oa-1"]["row_ids"], ["oa-1", "inv-1", "inv-2"])
        self.assertEqual(desired["CASE-OA-OFFSET-oa-1"]["row_types"], ["oa", "invoice", "invoice"])
        self.assertEqual(desired["CASE-OA-OFFSET-oa-1"]["month_scope"], "2026-03")
        self.assertEqual(
            desired["CASE-OA-OFFSET-oa-1"]["amount_check"],
            {"status": "matched", "row_counts": {"oa": 1, "bank": 0, "invoice": 2}},
        )

    def test_build_skips_unconfigured_applicant_missing_attachment_and_manual_conflict(self) -> None:
        payload = {
            "open": {
                "oa": [
                    {"id": "oa-unconfigured", "applicant": "李四", "month": "2026-03"},
                    {"id": "oa-missing-attachment", "applicant": "周洁莹", "month": "2026-03"},
                    {"id": "oa-conflict", "applicant": "周洁莹", "month": "2026-03"},
                ],
                "invoice": [
                    {
                        "id": "inv-conflict",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-conflict",
                        "month": "2026-03",
                    }
                ],
            }
        }

        desired = self._builder(conflict_row_ids={"oa-conflict"}).build(payload)

        self.assertEqual(desired, {})

    def test_build_uses_all_scope_when_related_rows_cross_months(self) -> None:
        payload = {
            "paired": {
                "oa": [{"id": "oa-1", "applicant": "周洁莹", "month": "2026-03"}],
                "invoice": [
                    {
                        "id": "inv-1",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-1",
                        "month": "2026-04",
                    }
                ],
            }
        }

        desired = self._builder().build(payload)

        self.assertEqual(desired["CASE-OA-OFFSET-oa-1"]["month_scope"], "all")

    def test_build_returns_empty_without_applicant_configuration(self) -> None:
        payload = {
            "open": {
                "oa": [{"id": "oa-1", "applicant": "周洁莹"}],
                "invoice": [
                    {"id": "inv-1", "source_kind": "oa_attachment_invoice", "derived_from_oa_id": "oa-1"}
                ],
            }
        }

        self.assertEqual(self._builder(applicant_names=[]).build(payload), {})


if __name__ == "__main__":
    unittest.main()
