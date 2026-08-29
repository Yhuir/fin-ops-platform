from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_relation_receipt_eligibility import (
    workbench_relation_receipt_action,
)


def _rows() -> dict[str, list[dict[str, object]]]:
    return {
        "oa": [],
        "bank": [{
            "id": "bank-1",
            "counterparty_name": "付款单位",
            "credit_amount": "100.00",
            "txn_direction": "inflow",
            "amount": "100.00",
            "trade_time": "2026-08-30T10:00:00+08:00",
            "currency": "人民币元",
        }],
        "invoice": [{
            "id": "invoice-1",
            "invoice_type": "output",
            "invoice_no": "INV-1",
            "currency": "CNY",
        }],
    }


class WorkbenchRelationReceiptEligibilityTests(unittest.TestCase):
    def test_exposes_one_action_for_income_and_output_invoice_relation_in_either_zone(self) -> None:
        self.assertEqual(
            workbench_relation_receipt_action(_rows(), case_id="CASE-1"),
            {
                "eligible": True,
                "case_id": "CASE-1",
                "action_label": "编辑并打印收据",
            },
        )

    def test_hides_action_outside_the_exact_relation_contract(self) -> None:
        cases = []
        with_oa = _rows()
        with_oa["oa"] = [{"id": "oa-1"}]
        cases.append(with_oa)
        outflow = _rows()
        outflow["bank"][0]["txn_direction"] = "outflow"
        cases.append(outflow)
        input_invoice = _rows()
        input_invoice["invoice"][0]["invoice_type"] = "input"
        cases.append(input_invoice)
        missing_payer = _rows()
        missing_payer["bank"][0]["counterparty_name"] = ""
        cases.append(missing_payer)
        missing_currency = _rows()
        missing_currency["bank"][0]["currency"] = None
        cases.append(missing_currency)
        missing_date = _rows()
        missing_date["bank"][0]["trade_time"] = None
        cases.append(missing_date)
        nonpositive_income = _rows()
        nonpositive_income["bank"][0]["amount"] = "0"
        cases.append(nonpositive_income)
        missing_invoice_number = _rows()
        missing_invoice_number["invoice"][0]["invoice_no"] = ""
        cases.append(missing_invoice_number)

        for rows in cases:
            with self.subTest(rows=rows):
                self.assertIsNone(
                    workbench_relation_receipt_action(rows, case_id="CASE-1")
                )


if __name__ == "__main__":
    unittest.main()
