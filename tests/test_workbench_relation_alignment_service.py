from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_relation_alignment_service import (
    WorkbenchRelationAlignmentService,
)


class WorkbenchRelationAlignmentServiceTests(unittest.TestCase):
    def test_aligns_exact_amount_and_unique_bank_sum_inside_multi_oa_relation(self) -> None:
        service = WorkbenchRelationAlignmentService()
        rows_by_id = {
            "oa-29350": oa_row("oa-29350", "29350.00"),
            "oa-88050": oa_row("oa-88050", "88050.00"),
            "bank-29350": bank_row("bank-29350", debit_amount="29350.00"),
            "bank-60000": bank_row("bank-60000", debit_amount="60000.00"),
            "bank-28050": bank_row("bank-28050", debit_amount="28050.00"),
        }

        alignment = service.align_relation(
            rows_by_id=rows_by_id,
            relation={"case_id": "CASE-MULTI-OA", "row_ids": list(rows_by_id)},
        )

        self.assertEqual(alignment["version"], 1)
        self.assertEqual(alignment["source"], "deterministic_relation_alignment")
        self.assertEqual(alignment["unresolved_row_ids"], [])
        self.assertEqual(
            alignment["links"],
            [
                {
                    "oa_row_id": "oa-29350",
                    "bank_row_ids": ["bank-29350"],
                    "invoice_row_ids": [],
                    "evidence": ["exact_amount", "same_active_relation"],
                },
                {
                    "oa_row_id": "oa-88050",
                    "bank_row_ids": ["bank-60000", "bank-28050"],
                    "invoice_row_ids": [],
                    "evidence": ["unique_bank_sum", "same_active_relation"],
                },
            ],
        )

    def test_preserves_invoice_attachment_source_and_normalizes_item_id_to_parent_oa(self) -> None:
        service = WorkbenchRelationAlignmentService()
        rows_by_id = {
            "oa-parent": oa_row("oa-parent", "1968.00"),
            "inv-attachment": invoice_row(
                "inv-attachment",
                "1968.00",
                derived_from_oa_id="oa-parent:item:4:de54f988bd66",
            ),
        }

        alignment = service.align_relation(
            rows_by_id=rows_by_id,
            relation={"case_id": "CASE-INVOICE-SOURCE", "row_ids": list(rows_by_id)},
        )

        self.assertEqual(
            alignment["links"],
            [
                {
                    "oa_row_id": "oa-parent",
                    "bank_row_ids": [],
                    "invoice_row_ids": ["inv-attachment"],
                    "evidence": ["invoice_source_oa", "same_active_relation"],
                }
            ],
        )
        self.assertEqual(alignment["unresolved_row_ids"], [])

    def test_resolves_attachment_source_alias_to_canonical_oa_row(self) -> None:
        service = WorkbenchRelationAlignmentService()
        rows_by_id = {
            "oa-exp-2206": {
                **oa_row("oa-exp-2206", "413.00"),
                "detail_fields": {"Mongo文档ID": "6a0ee8613bb8164165d8c61a"},
            },
            "inv_imported_0058": invoice_row(
                "inv_imported_0058",
                "60.00",
                derived_from_oa_id="oa-exp-6a0ee8613bb8164165d8c61a:item:2:9ca59ea6e4ab",
            ),
        }

        alignment = service.align_relation(
            rows_by_id=rows_by_id,
            relation={"case_id": "CASE-OA-ALIAS", "row_ids": list(rows_by_id)},
        )

        self.assertEqual(
            alignment["links"],
            [
                {
                    "oa_row_id": "oa-exp-2206",
                    "bank_row_ids": [],
                    "invoice_row_ids": ["inv_imported_0058"],
                    "evidence": ["invoice_source_oa", "same_active_relation"],
                }
            ],
        )

    def test_leaves_ambiguous_duplicate_amounts_unresolved_instead_of_guessing(self) -> None:
        service = WorkbenchRelationAlignmentService()
        rows_by_id = {
            "oa-a": oa_row("oa-a", "29350.00"),
            "oa-b": oa_row("oa-b", "29350.00"),
            "bank-29350": bank_row("bank-29350", debit_amount="29350.00"),
        }

        alignment = service.align_relation(
            rows_by_id=rows_by_id,
            relation={"case_id": "CASE-AMBIGUOUS", "row_ids": list(rows_by_id)},
        )

        self.assertEqual(alignment["links"], [])
        self.assertEqual(alignment["unresolved_row_ids"], ["bank-29350"])
        self.assertEqual(
            alignment["diagnostics"],
            [
                {
                    "code": "ambiguous_bank_exact_amount",
                    "row_id": "bank-29350",
                    "candidate_oa_row_ids": ["oa-a", "oa-b"],
                }
            ],
        )

    def test_large_bank_relation_uses_bounded_unique_sum_matching(self) -> None:
        service = WorkbenchRelationAlignmentService()
        rows_by_id = {
            "oa-target": oa_row("oa-target", "300.00"),
            "bank-100": bank_row("bank-100", debit_amount="100.00"),
            "bank-200": bank_row("bank-200", debit_amount="200.00"),
            **{
                f"bank-large-{index}": bank_row(f"bank-large-{index}", debit_amount=f"{1000 + index}.00")
                for index in range(40)
            },
        }

        alignment = service.align_relation(
            rows_by_id=rows_by_id,
            relation={"case_id": "CASE-LARGE-RELATION", "row_ids": list(rows_by_id)},
        )

        self.assertEqual(alignment["unresolved_row_ids"], [])
        self.assertEqual(
            alignment["links"],
            [
                {
                    "oa_row_id": "oa-target",
                    "bank_row_ids": ["bank-100", "bank-200"],
                    "invoice_row_ids": [],
                    "evidence": ["unique_bank_sum", "same_active_relation"],
                }
            ],
        )

    def test_ambiguous_bank_sum_does_not_guess_subset(self) -> None:
        service = WorkbenchRelationAlignmentService()
        rows_by_id = {
            "oa-target": oa_row("oa-target", "300.00"),
            "bank-100": bank_row("bank-100", debit_amount="100.00"),
            "bank-200": bank_row("bank-200", debit_amount="200.00"),
            "bank-120": bank_row("bank-120", debit_amount="120.00"),
            "bank-180": bank_row("bank-180", debit_amount="180.00"),
        }

        alignment = service.align_relation(
            rows_by_id=rows_by_id,
            relation={"case_id": "CASE-AMBIGUOUS-SUM", "row_ids": list(rows_by_id)},
        )

        self.assertEqual(alignment["links"], [])


def oa_row(row_id: str, amount: str) -> dict[str, object]:
    return {"id": row_id, "type": "oa", "amount": amount}


def bank_row(row_id: str, *, debit_amount: str = "", credit_amount: str = "") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "amount": debit_amount or credit_amount,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
    }


def invoice_row(row_id: str, amount: str, *, derived_from_oa_id: str) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "invoice",
        "amount": amount,
        "derived_from_oa_id": derived_from_oa_id,
    }
