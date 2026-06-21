from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_attachment_recognition_service import (
    CREATE_INVOICE_AND_LINK,
    IGNORE,
    LINK_EXISTING_INVOICE,
    InvoiceAttachmentRecognitionService,
)


class InvoiceAttachmentRecognitionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.counterparty = Counterparty(
            id="cp_001",
            name="云南溯源科技有限公司",
            normalized_name="云南溯源科技有限公司",
            counterparty_type="customer",
        )
        self.existing_invoice = Invoice(
            id="inv_existing_001",
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
        self.repository = ImportNormalizationService(existing_invoices=[self.existing_invoice])
        self.service = InvoiceAttachmentRecognitionService(invoice_repository=self.repository)

    def test_formal_attachment_with_existing_identity_links_existing_invoice(self) -> None:
        decision = self.service.decide(
            {
                "evidence_type": "tax_invoice",
                "digital_invoice_no": "26532000000141671581",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "total_with_tax": "400.00",
            }
        )

        self.assertEqual(decision.action, LINK_EXISTING_INVOICE)
        self.assertEqual(decision.invoice, self.existing_invoice)
        self.assertEqual(decision.identity_key, "26532000000141671581")

    def test_formal_attachment_with_ambiguous_existing_identity_is_ignored(self) -> None:
        duplicate_invoice = Invoice(
            id="inv_existing_duplicate",
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
            source_unique_key="duplicate-source-key",
        )
        service = InvoiceAttachmentRecognitionService(
            invoice_repository=ImportNormalizationService(
                existing_invoices=[self.existing_invoice, duplicate_invoice]
            )
        )

        decision = service.decide(
            {
                "evidence_type": "tax_invoice",
                "digital_invoice_no": "26532000000141671581",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "total_with_tax": "400.00",
            }
        )

        self.assertEqual(decision.action, IGNORE)
        self.assertEqual(decision.reason, "ambiguous_invoice_identity")
        self.assertEqual(decision.identity_key, "26532000000141671581")

    def test_formal_attachment_not_in_pool_can_create_and_link(self) -> None:
        decision = self.service.decide(
            {
                "evidence_type": "tax_invoice",
                "invoice_code": "053001",
                "invoice_no": "90010001",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "total_with_tax": "400.00",
            }
        )

        self.assertEqual(decision.action, CREATE_INVOICE_AND_LINK)
        self.assertTrue(decision.allow_create)
        self.assertEqual(decision.identity_key, "053001:90010001")

    def test_formal_document_kind_without_evidence_type_can_create_and_link(self) -> None:
        decision = self.service.decide(
            {
                "document_kind": "digital_invoice",
                "invoice_code": "053001",
                "invoice_no": "90010001",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "total_with_tax": "400.00",
            }
        )

        self.assertEqual(decision.action, CREATE_INVOICE_AND_LINK)
        self.assertEqual(decision.identity_key, "053001:90010001")

    def test_unknown_evidence_with_full_invoice_identity_is_ignored(self) -> None:
        decision = self.service.decide(
            {
                "evidence_type": "unknown",
                "digital_invoice_no": "26532000000141671583",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "total_with_tax": "400.00",
            }
        )

        self.assertEqual(decision.action, IGNORE)
        self.assertEqual(decision.reason, "not_formal_invoice")

    def test_missing_evidence_type_with_full_invoice_identity_is_ignored(self) -> None:
        decision = self.service.decide(
            {
                "digital_invoice_no": "26532000000141671583",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "total_with_tax": "400.00",
            }
        )

        self.assertEqual(decision.action, IGNORE)
        self.assertEqual(decision.reason, "not_formal_invoice")

    def test_non_tax_receipt_is_ignored(self) -> None:
        decision = self.service.decide(
            {
                "evidence_type": "non_tax_receipt",
                "document_kind": "non_tax_receipt",
                "seller_name": "云南省财政厅",
                "issue_date": "2026-01-27",
                "total_with_tax": "400.00",
            }
        )

        self.assertEqual(decision.action, IGNORE)

    def test_traffic_payment_ticket_is_ignored(self) -> None:
        decision = self.service.decide(
            {
                "evidence_type": "tax_invoice",
                "invoice_no": "012345",
                "seller_name": "昆明市公安局交通管理支队",
                "invoice_kind": "交通违法罚款缴款书",
                "issue_date": "2026-01-27",
                "total_with_tax": "100.00",
            }
        )

        self.assertEqual(decision.action, IGNORE)

    def test_incomplete_ocr_identity_is_ignored(self) -> None:
        decision = self.service.decide(
            {
                "evidence_type": "tax_invoice",
                "invoice_no": "90010001",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "total_with_tax": "400.00",
            }
        )

        self.assertEqual(decision.action, IGNORE)


if __name__ == "__main__":
    unittest.main()
