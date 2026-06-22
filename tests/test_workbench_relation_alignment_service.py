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
