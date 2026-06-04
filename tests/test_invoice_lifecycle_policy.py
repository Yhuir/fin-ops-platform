from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.services.input_invoice_usage_payment_rules import StaticInputInvoiceUsagePaymentRulesProvider
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy


class InvoiceLifecyclePolicyTests(unittest.TestCase):
    def test_unifies_pending_invoice_acquisition_status_shape(self) -> None:
        policy = InvoiceLifecyclePolicy()

        status = policy.evaluate_pending_invoice_acquisition(
            direction="expense",
            group=None,
            has_invoices=True,
            payment_summary={"invoice_total": "196.00", "paid_total": "100.00"},
            matched_rule=None,
        )

        self.assertEqual(status["code"], "invoice_not_fully_paid")
        self.assertEqual(status["label"], "未支付完已开票")
        self.assertEqual(status["primary_action"], "view_relation")

    def test_unifies_input_invoice_payment_status_with_configurable_rules(self) -> None:
        policy = InvoiceLifecyclePolicy(input_payment_rules_provider=StaticInputInvoiceUsagePaymentRulesProvider())

        status = policy.evaluate_input_invoice_payment(
            has_oa=True,
            has_bank=True,
            applicant_name="田孟维",
            fully_matched=True,
            invoice_oa_amount_matched=True,
        )

        self.assertEqual(status["code"], "paid")
        self.assertEqual(status["label"], "已付款")

    def test_unifies_output_invoice_collection_status(self) -> None:
        policy = InvoiceLifecyclePolicy()

        status = policy.evaluate_output_invoice_collection(
            invoice_total=Decimal("100.00"),
            own_inflow_total=Decimal("60.00"),
            related_inflow_total=Decimal("0.00"),
            related_outflow_total=Decimal("0.00"),
            has_red_relation=False,
            fully_matched=False,
        )

        self.assertEqual(status["code"], "partial_collected")
        self.assertEqual(status["collectedAmount"], "60.00")
        self.assertEqual(status["pendingAmount"], "40.00")

    def test_unifies_tax_certification_status(self) -> None:
        policy = InvoiceLifecyclePolicy()

        certified = policy.evaluate_tax_certification(is_certified=True, certified_item={"id": "cert-1"})
        pending = policy.evaluate_tax_certification(is_certified=False)

        self.assertEqual(certified["code"], "certified")
        self.assertEqual(certified["label"], "已认证")
        self.assertEqual(certified["certified_status"], "已认证")
        self.assertEqual(pending["code"], "pending_certification")
        self.assertEqual(pending["certified_status"], "待认证")


if __name__ == "__main__":
    unittest.main()
