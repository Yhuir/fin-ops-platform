from __future__ import annotations

import unittest
from decimal import Decimal

from fin_ops_platform.services.input_invoice_usage_payment_rules import AppSettingsInputInvoiceUsagePaymentRulesProvider
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
        policy = InvoiceLifecyclePolicy(input_payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None))

        status = policy.evaluate_input_invoice_payment(
            has_oa=True,
            has_bank=True,
            applicant_name="田孟维",
            fully_matched=True,
            invoice_oa_amount_matched=True,
        )

        self.assertEqual(status["code"], "paid")
        self.assertEqual(status["label"], "已付款")

    def test_input_invoice_payment_requires_explicit_rules_provider(self) -> None:
        policy = InvoiceLifecyclePolicy()

        with self.assertRaisesRegex(
            ValueError,
            "input_payment_rules_provider is required for input invoice usage payment evaluation",
        ):
            policy.evaluate_input_invoice_payment(
                has_oa=True,
                has_bank=True,
                applicant_name="田孟维",
                fully_matched=True,
                invoice_oa_amount_matched=True,
            )

    def test_unifies_tax_certification_status(self) -> None:
        policy = InvoiceLifecyclePolicy()

        certified = policy.evaluate_tax_certification(is_certified=True, certified_item={"id": "cert-1"})
        pending = policy.evaluate_tax_certification(is_certified=False)

        self.assertEqual(certified["code"], "certified")
        self.assertEqual(certified["label"], "已认证")
        self.assertEqual(certified["certified_status"], "已认证")
        self.assertEqual(pending["code"], "pending_certification")
        self.assertEqual(pending["certified_status"], "待认证")

    def test_oa_payment_statuses_only_expose_paid_or_unpaid(self) -> None:
        policy = InvoiceLifecyclePolicy()

        statuses = [
            policy.evaluate_oa_payment(oa_amount=Decimal("100.00"), paid_total=Decimal("0.00"), has_bank=False),
            policy.evaluate_oa_payment(oa_amount=Decimal("100.00"), paid_total=Decimal("100.00"), has_bank=True),
            policy.evaluate_oa_payment(oa_amount=Decimal("100.00"), paid_total=Decimal("80.00"), has_bank=True),
            policy.evaluate_oa_payment(oa_amount=Decimal("100.00"), paid_total=Decimal("120.00"), has_bank=True),
            policy.evaluate_oa_payment(
                oa_amount=Decimal("150.00"),
                paid_total=Decimal("150.00"),
                has_bank=True,
                merged_payment=True,
            ),
        ]

        self.assertEqual(
            [status["code"] for status in statuses],
            ["unpaid", "paid", "paid", "paid", "paid"],
        )
        for status in statuses:
            self.assertIn(status["code"], {"paid", "unpaid"})
            self.assertNotIn(status["code"], {"overpaid", "merged_paid", "partially_paid", "pending_review"})
            self.assertNotIn("支付多了", status["label"])
            self.assertNotIn("支付少了", status["label"])
            self.assertNotIn("待核对", status["label"])
            self.assertNotIn("多条OA合并支付", status["label"])


if __name__ == "__main__":
    unittest.main()
