from decimal import Decimal
import unittest
from unittest.mock import patch

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.tools.oa_attachment_invoice_promotion import (
    OAAttachmentInvoiceCandidate,
    _load_candidates,
    audit_oa_attachment_invoice_promotion,
    main,
)


class OAAttachmentInvoicePromotionToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.counterparty = Counterparty(
            id="cp-001",
            name="云南溯源科技有限公司",
            normalized_name="云南溯源科技有限公司",
            counterparty_type="customer",
        )
        self.existing_invoice = Invoice(
            id="invoice-existing-001",
            invoice_type=InvoiceType.INPUT,
            invoice_no="26532000000141671581",
            digital_invoice_no="26532000000141671581",
            counterparty=self.counterparty,
            amount=Decimal("400.00"),
            signed_amount=Decimal("400.00"),
            invoice_date="2026-01-27",
            total_with_tax=Decimal("400.00"),
            seller_name="云南建筑技术发展中心",
            buyer_name="云南溯源科技有限公司",
            source_unique_key="26532000000141671581",
        )

    def test_dry_run_reports_links_and_creates_without_persisting(self) -> None:
        candidates = [
            self._candidate(
                0,
                {
                    "evidence_type": "tax_invoice",
                    "digital_invoice_no": "26532000000141671581",
                    "seller_name": "云南建筑技术发展中心",
                    "buyer_name": "云南溯源科技有限公司",
                    "issue_date": "2026-01-27",
                    "total_with_tax": "400.00",
                    "source_attachment_key": "attachment-existing",
                },
            ),
            self._candidate(
                1,
                {
                    "evidence_type": "tax_invoice",
                    "digital_invoice_no": "26532000000141671582",
                    "seller_name": "云南建筑技术发展中心",
                    "buyer_name": "云南溯源科技有限公司",
                    "issue_date": "2026-01-28",
                    "total_with_tax": "500.00",
                    "source_attachment_key": "attachment-new",
                },
            ),
            self._candidate(
                2,
                {
                    "evidence_type": "payment_receipt",
                    "seller_name": "云南建筑技术发展中心",
                    "buyer_name": "云南溯源科技有限公司",
                    "issue_date": "2026-01-29",
                    "total_with_tax": "600.00",
                    "source_attachment_key": "attachment-receipt",
                },
            ),
        ]

        with (
            patch(
                "fin_ops_platform.tools.oa_attachment_invoice_promotion._fetch_all_invoices",
                return_value=[self.existing_invoice],
            ),
            patch(
                "fin_ops_platform.tools.oa_attachment_invoice_promotion._load_candidates",
                return_value=candidates,
            ),
            patch("fin_ops_platform.tools.oa_attachment_invoice_promotion._persist_affected_invoices") as persist,
        ):
            report = audit_oa_attachment_invoice_promotion(connection=object(), example_limit=10)

        persist.assert_not_called()
        self.assertFalse(report["summary"]["persisted"])
        self.assertEqual(report["summary"]["existing_invoice_count"], 1)
        self.assertEqual(report["summary"]["linked_existing_invoice_count"], 1)
        self.assertEqual(report["summary"]["created_invoice_count"], 1)
        self.assertEqual(report["summary"]["final_in_memory_invoice_count"], 2)
        self.assertEqual(report["reason_counts"]["matched_existing_invoice"], 1)
        self.assertEqual(report["reason_counts"]["formal_invoice_not_in_pool"], 1)
        self.assertEqual(report["reason_counts"]["not_formal_invoice"], 1)

    def test_apply_requires_explicit_confirmation_flag(self) -> None:
        from io import StringIO

        stdout = StringIO()

        exit_code = main(["--apply"], stdout=stdout)

        self.assertEqual(exit_code, 2)
        self.assertIn("--confirm-apply-oa-attachment-invoices", stdout.getvalue())

    def test_load_candidates_does_not_infer_missing_parent_oa_from_item_id(self) -> None:
        class FakeConnection:
            def fetch_all(self, sql: str) -> list[dict[str, object]]:
                return [
                    {
                        "cache_source_attachment_key": "cache-key-1",
                        "invoices": [
                            {
                                "evidence_type": "tax_invoice",
                                "digital_invoice_no": "26532000000141671582",
                                "seller_name": "云南建筑技术发展中心",
                                "buyer_name": "云南溯源科技有限公司",
                                "issue_date": "2026-01-28",
                                "total_with_tax": "500.00",
                            }
                        ],
                        "oa_application_id": None,
                        "oa_source_id": "oa-exp-orphan",
                        "oa_row_id": None,
                        "source_expense_item_id": "oa-exp-orphan:item:2:abcdef",
                        "source_expense_row_index": "2",
                        "source_attachment_key": "attachment-orphan",
                        "source_attachment_name": "orphan.pdf",
                    }
                ]

        candidates = _load_candidates(FakeConnection())

        self.assertEqual(len(candidates), 1)
        self.assertIsNone(candidates[0].oa_row_id)
        self.assertIsNone(candidates[0].source_workbench_row_id)

    @staticmethod
    def _candidate(index: int, attachment_invoice: dict[str, object]) -> OAAttachmentInvoiceCandidate:
        return OAAttachmentInvoiceCandidate(
            cache_source_attachment_key=f"cache-{index}",
            invoice_index=index,
            attachment_invoice=attachment_invoice,
            oa_form_id="oa-form-001",
            oa_row_id="oa-exp-001",
            source_workbench_row_id=f"oa-att-inv-oa-exp-001-{index}",
            context={},
        )


if __name__ == "__main__":
    unittest.main()
