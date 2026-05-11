import unittest

from fin_ops_platform.services.workbench_exception_classifier import WorkbenchExceptionClassifier


class WorkbenchExceptionClassifierTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = WorkbenchExceptionClassifier()

    def test_oa_bank_equal_without_input_invoice_waits_for_invoice(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [oa_row("oa-1", "100.00"), expense_bank_row("bank-1", "100.00")],
            }
        )

        self.assertEqual(result["scenario_code"], "expense_oa_bank_missing_input_invoice_equal")
        self.assertEqual(result["amount_summary"]["expense_relation"], "oa_equals_bank_missing_input_invoice")
        self.assertEqual(action_codes(result["available_actions"]), ["wait_input_invoice"])
        self.assertEqual(result["workflow_projection"]["state"], "WAIT_INPUT_INVOICE")
        self.assertIn("ADD_INPUT_INVOICE", result["workflow_projection"]["allowed_next_events"])

    def test_expense_all_equal_confirms_closed(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [
                    oa_row("oa-1", "100.00"),
                    expense_bank_row("bank-1", "100.00"),
                    input_invoice_row("invoice-1", "100.00"),
                ],
            }
        )

        self.assertEqual(result["scenario_code"], "expense_all_equal")
        self.assertEqual(result["amount_summary"]["expense_relation"], "all_equal")
        self.assertEqual(action_codes(result["automatic_actions"]), ["confirm_closed"])
        self.assertEqual(result["workflow_projection"]["state"], "CLOSED")

    def test_oa_bank_equal_greater_than_input_invoice_continues_invoice_chasing(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [
                    oa_row("oa-1", "100.00"),
                    expense_bank_row("bank-1", "100.00"),
                    input_invoice_row("invoice-1", "80.00"),
                ],
            }
        )

        self.assertEqual(result["scenario_code"], "expense_oa_bank_equal_input_invoice_less")
        self.assertEqual(result["amount_summary"]["expense_relation"], "oa_equals_bank_greater_than_input_invoice")
        self.assertEqual(action_codes(result["available_actions"]), ["continue_wait_input_invoice"])

    def test_oa_bank_equal_less_than_input_invoice_requests_owner_confirmation(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [
                    oa_row("oa-1", "100.00"),
                    expense_bank_row("bank-1", "100.00"),
                    input_invoice_row("invoice-1", "120.00"),
                ],
            }
        )

        self.assertEqual(result["scenario_code"], "expense_oa_bank_equal_input_invoice_more")
        self.assertEqual(result["amount_summary"]["expense_relation"], "oa_equals_bank_less_than_input_invoice")
        self.assertEqual(action_codes(result["available_actions"]), ["confirm_extra_invoice_owner"])

    def test_bank_input_invoice_equal_without_oa_offers_structured_manual_oa_exemption(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [expense_bank_row("bank-1", "100.00"), input_invoice_row("invoice-1", "100.00")],
            }
        )

        self.assertEqual(result["scenario_code"], "expense_bank_input_invoice_missing_oa_equal")
        self.assertEqual(result["amount_summary"]["expense_relation"], "bank_equals_input_invoice_missing_oa")
        self.assertEqual(
            action_codes(result["available_actions"]),
            ["confirm_oa_exempt_manual", "request_missing_oa"],
        )
        exemption_action = result["available_actions"][0]
        self.assertEqual(exemption_action["payload_template"]["relation_mode"], "oa_exempt")
        self.assertEqual(exemption_action["payload_template"]["oa_exemption"]["source"], "manual")

    def test_only_bank_fee_bank_row_returns_structured_auto_oa_exemption(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [
                    expense_bank_row(
                        "bank-fee",
                        "12.00",
                        summary="网银手续费",
                        counterparty_name="招商银行",
                    )
                ],
            }
        )

        self.assertEqual(result["scenario_code"], "expense_only_bank_auto_oa_exempt")
        self.assertEqual(action_codes(result["automatic_actions"]), ["confirm_oa_exempt_auto"])
        oa_exemption = result["automatic_actions"][0]["payload"]["oa_exemption"]
        self.assertEqual(oa_exemption["source"], "auto")
        self.assertEqual(oa_exemption["reason_code"], "bank_fee")
        self.assertEqual(oa_exemption["rule_version"], "exception_rules_v1")

    def test_income_bank_output_invoice_equal_confirms_income_closed(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [income_bank_row("bank-1", "100.00"), output_invoice_row("invoice-1", "100.00")],
            }
        )

        self.assertEqual(result["business_line"], "income")
        self.assertEqual(result["scenario_code"], "income_bank_output_invoice_equal")
        self.assertEqual(result["amount_summary"]["income_relation"], "income_equals_invoice")
        self.assertEqual(action_codes(result["automatic_actions"]), ["confirm_income_closed"])

    def test_income_bank_more_than_output_invoice_requests_refund_or_more_invoice(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [income_bank_row("bank-1", "120.00"), output_invoice_row("invoice-1", "100.00")],
            }
        )

        self.assertEqual(result["scenario_code"], "income_bank_more_than_output_invoice")
        self.assertEqual(result["amount_summary"]["income_relation"], "income_greater_than_invoice")
        self.assertEqual(action_codes(result["available_actions"]), ["confirm_refund_or_more_invoice"])

    def test_output_invoice_more_than_income_bank_waits_collection(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [income_bank_row("bank-1", "80.00"), output_invoice_row("invoice-1", "100.00")],
            }
        )

        self.assertEqual(result["scenario_code"], "income_output_invoice_more_than_bank")
        self.assertEqual(result["amount_summary"]["income_relation"], "income_less_than_invoice")
        self.assertEqual(action_codes(result["available_actions"]), ["wait_collection"])

    def test_income_selection_with_oa_is_data_anomaly(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [oa_row("oa-1", "100.00"), income_bank_row("bank-1", "100.00")],
            }
        )

        self.assertEqual(result["business_line"], "data_anomaly")
        self.assertEqual(result["scenario_code"], "income_contains_oa_data_anomaly")
        self.assertEqual(action_codes(result["available_actions"]), ["income_data_anomaly_manual_review"])
        self.assertTrue(result["warnings"])

    def test_unknown_bank_direction_requires_manual_review(self) -> None:
        result = self.classifier.preview(
            {
                "month": "2026-05",
                "rows": [{"id": "bank-unknown", "type": "bank", "amount": "100.00"}],
            }
        )

        self.assertEqual(result["scenario_code"], "data_anomaly_unknown_direction")
        self.assertEqual(result["amount_summary"]["has_unknown_direction"], True)
        self.assertEqual(result["amount_summary"]["unknown_direction_row_ids"], ["bank-unknown"])
        self.assertEqual(action_codes(result["available_actions"]), ["manual_review"])


def action_codes(actions: list[dict[str, object]]) -> list[str]:
    return [str(action["action_code"]) for action in actions]


def oa_row(row_id: str, amount: str) -> dict[str, str]:
    return {
        "id": row_id,
        "type": "oa",
        "apply_type": "付款申请",
        "amount": amount,
    }


def expense_bank_row(
    row_id: str,
    amount: str,
    *,
    summary: str = "付款",
    counterparty_name: str = "供应商A",
) -> dict[str, str]:
    return {
        "id": row_id,
        "type": "bank",
        "debit_amount": amount,
        "credit_amount": "",
        "summary": summary,
        "counterparty_name": counterparty_name,
    }


def income_bank_row(row_id: str, amount: str) -> dict[str, str]:
    return {
        "id": row_id,
        "type": "bank",
        "debit_amount": "",
        "credit_amount": amount,
        "summary": "收款",
        "counterparty_name": "客户A",
    }


def input_invoice_row(row_id: str, amount: str) -> dict[str, str]:
    return {
        "id": row_id,
        "type": "invoice",
        "invoice_type": "input",
        "total_with_tax": amount,
    }


def output_invoice_row(row_id: str, amount: str) -> dict[str, str]:
    return {
        "id": row_id,
        "type": "invoice",
        "invoice_type": "output",
        "total_with_tax": amount,
    }


if __name__ == "__main__":
    unittest.main()
