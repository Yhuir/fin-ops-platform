from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import Counterparty, Invoice
from fin_ops_platform.services.app_settings_service import (
    OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
    OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED,
    OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
)
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import (
    OAAttachmentInvoicePromotionService,
)


class OAAttachmentInvoicePromotionServiceTests(unittest.TestCase):
    def test_links_every_invoice_to_its_expense_item_in_one_batch_query(self) -> None:
        payloads = [
            _attachment("26539150014000401220", "145.00", "item-0", "outbound.pdf"),
            _attachment("26539148197001628598", "145.00", "item-0", "return.pdf"),
            _attachment("26532000000000000482", "482.00", "item-1", "meal.pdf"),
            _attachment("26532000000000000018", "18.00", "item-2", "post.pdf"),
            _attachment("26532000000000000290", "290.00", "item-3", "fuel.pdf"),
        ]
        repository = FakeInvoiceRepository([_invoice(payload) for payload in payloads])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-2321",
            month="2026-06",
            attachment_invoices=payloads,
            attachment_evidences=[],
        )

        first = service.promote_records([record])
        second = service.promote_records([record])

        self.assertEqual(repository.identity_query_count, 2)
        self.assertEqual(first["summary"]["cache_candidate_count"], 5)
        self.assertEqual(first["summary"]["linked_existing_invoice_count"], 5)
        self.assertEqual(first["summary"]["affected_invoice_count"], 5)
        self.assertEqual(len(repository.save_calls), 1)
        self.assertEqual(second["summary"]["affected_invoice_count"], 0)
        self.assertEqual(second["reason_counts"], {"already_linked": 5})
        linked_items = [
            invoice.source_links[0]["source_expense_item_id"]
            for invoice in repository.invoices
        ]
        self.assertEqual(linked_items, ["item-0", "item-0", "item-1", "item-2", "item-3"])

    def test_preloads_existing_invoice_when_attachment_only_has_bare_20_digit_invoice_no(self) -> None:
        payload = _attachment("26539150014000401220", "145.00", "item-0", "outbound.pdf")
        payload.pop("digital_invoice_no")
        existing = _invoice({**payload, "digital_invoice_no": payload["invoice_no"]})
        repository = FakeInvoiceRepository([existing])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-2321",
            month="2026-06",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        report = service.promote_records([record])

        self.assertEqual(report["summary"]["existing_invoice_count"], 1)
        self.assertEqual(report["summary"]["linked_existing_invoice_count"], 1)
        self.assertEqual(report["summary"]["created_invoice_count"], 0)
        self.assertEqual(repository.invoices[0].id, existing.id)

    def test_create_mode_creates_missing_formal_invoice_and_disabled_mode_writes_nothing(self) -> None:
        payload = _attachment("26532000000000000600", "600.00", "item-1", "invoice.pdf")
        repository = FakeInvoiceRepository([])
        create_service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
        )
        record = SimpleNamespace(
            id="oa-exp-create",
            month="2026-03",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        created = create_service.promote_records([record])
        disabled = create_service.promote_candidates(
            create_service.candidates_from_records([record]),
            promotion_mode=OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED,
            apply=True,
        )

        self.assertEqual(created["summary"]["created_invoice_count"], 1)
        self.assertEqual(created["summary"]["affected_invoice_count"], 1)
        self.assertEqual(repository.invoices[0].source_links[0]["derived_from_oa_id"], "oa-exp-create")
        self.assertEqual(disabled["reason_counts"], {"promotion_disabled": 1})
        self.assertEqual(len(repository.save_calls), 1)

    def test_rejects_reusing_one_invoice_across_different_oa_source_contexts(self) -> None:
        payload = _attachment("26532000000000000700", "700.00", "item-new", "invoice.pdf")
        invoice = _invoice(payload)
        invoice.source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "source_id": "old.pdf",
                "batch_id": "",
                "derived_from_oa_id": "oa-exp-old",
                "source_expense_item_id": "item-old",
            }
        ]
        repository = FakeInvoiceRepository([invoice])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-new",
            month="2026-03",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        report = service.promote_records([record])

        self.assertEqual(report["reason_counts"], {"source_context_conflict": 1})
        self.assertEqual(report["summary"]["affected_invoice_count"], 0)
        self.assertEqual(repository.save_calls, [])

    def test_enriches_legacy_parent_link_with_expense_item_context(self) -> None:
        payload = _attachment("26532000000000000800", "800.00", "item-2", "invoice.pdf")
        invoice = _invoice(payload)
        invoice.source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "source_id": payload["source_attachment_key"],
                "batch_id": "",
                "derived_from_oa_id": "oa-exp-2321",
                "source_workbench_row_id": "legacy-parent-row",
            }
        ]
        repository = FakeInvoiceRepository([invoice])
        service = OAAttachmentInvoicePromotionService(
            invoice_repository=repository,
            promotion_mode_provider=lambda: OA_ATTACHMENT_INVOICE_PROMOTION_LINK_EXISTING_ONLY,
        )
        record = SimpleNamespace(
            id="oa-exp-2321",
            month="2026-06",
            attachment_invoices=[payload],
            attachment_evidences=[],
        )

        report = service.promote_records([record])

        self.assertEqual(report["summary"]["affected_invoice_count"], 1)
        self.assertEqual(invoice.source_links[0]["source_expense_item_id"], "item-2")
        self.assertNotEqual(invoice.source_links[0]["source_workbench_row_id"], "legacy-parent-row")


class FakeInvoiceRepository:
    def __init__(self, invoices: list[Invoice]) -> None:
        self.invoices = list(invoices)
        self.identity_query_count = 0
        self.save_calls: list[list[Invoice]] = []

    def find_invoices_by_identity_keys(self, *, canonical_keys: set[str]) -> list[Invoice]:
        self.identity_query_count += 1
        return [
            invoice
            for invoice in self.invoices
            if invoice.source_unique_key in canonical_keys or invoice.digital_invoice_no in canonical_keys
        ]

    def save_invoices(self, invoices: list[Invoice]) -> None:
        self.save_calls.append(list(invoices))
        by_id = {invoice.id: invoice for invoice in self.invoices}
        by_id.update({invoice.id: invoice for invoice in invoices})
        self.invoices = list(by_id.values())


def _attachment(invoice_no: str, amount: str, item_id: str, filename: str) -> dict[str, str]:
    return {
        "evidence_type": "tax_invoice",
        "document_kind": "digital_invoice",
        "digital_invoice_no": invoice_no,
        "invoice_no": invoice_no,
        "seller_name": "测试销方",
        "buyer_name": "云南溯源科技有限公司",
        "issue_date": "2026-06-29",
        "amount": amount,
        "total_with_tax": amount,
        "source_attachment_key": f"oa-exp-2321:{filename}",
        "source_attachment_name": filename,
        "source_expense_item_id": item_id,
    }


def _invoice(payload: dict[str, str]) -> Invoice:
    invoice_no = payload["digital_invoice_no"]
    counterparty = Counterparty(
        id=f"cp-{invoice_no}",
        name="测试销方",
        normalized_name="测试销方",
        counterparty_type="supplier",
    )
    return Invoice(
        id=f"invoice-{invoice_no}",
        invoice_type=InvoiceType.INPUT,
        invoice_no=invoice_no,
        digital_invoice_no=invoice_no,
        counterparty=counterparty,
        amount=Decimal(payload["amount"]),
        signed_amount=Decimal(payload["amount"]),
        invoice_date=payload["issue_date"],
        source_unique_key=invoice_no,
    )


if __name__ == "__main__":
    unittest.main()
