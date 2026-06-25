from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.workbench_canonical_oa_attachment_invoice_row_builder import (
    WorkbenchCanonicalOaAttachmentInvoiceRowBuilder,
)


class WorkbenchCanonicalOaAttachmentInvoiceRowBuilderTests(unittest.TestCase):
    def test_build_creates_canonical_invoice_row_with_tags_source_fields_and_summary(self) -> None:
        invoice = SimpleNamespace(
            id="invoice-1",
            invoice_type="output",
            invoice_no="NO-1",
            digital_invoice_no="D-1",
            invoice_code="C-1",
            invoice_date="2026-03-02",
            seller_tax_no="SELLER-TAX",
            seller_name="Seller",
            buyer_tax_no="BUYER-TAX",
            buyer_name="Buyer",
            amount=100,
            tax_amount=6,
            total_with_tax=None,
            tax_rate="6%",
            tags=["Existing"],
            source_links=[{"source_type": "manual_invoice_import", "foo": "bar"}],
            oa_form_id="oa-1",
        )
        source_link = {
            "derived_from_oa_id": "oa-1",
            "source_workbench_row_id": "oa-att-inv-1",
            "source_attachment_key": "att-1",
            "source_attachment_name": "invoice.pdf",
            "source_expense_item_id": "item-1",
        }
        builder = WorkbenchCanonicalOaAttachmentInvoiceRowBuilder(
            money_text=lambda value: "MISSING" if value is None else f"{value}",
            first_month_from_oa_row=lambda row: "2026-03",
            output_invoice_type_value="output",
        )

        row = builder.build(
            invoice,
            source_link=source_link,
            oa_row={"detail_fields": {"OA单号": "OA-001"}},
        )

        self.assertEqual(row["id"], "invoice-1")
        self.assertEqual(row["invoice_type"], "销项发票")
        self.assertEqual(row["amount"], "100")
        self.assertEqual(row["total_with_tax"], "100")
        self.assertEqual(row["tags"], ["Existing", "人工导入", "OA附件"])
        self.assertEqual(row["derived_from_oa_id"], "oa-1")
        self.assertEqual(row["source_workbench_row_id"], "oa-att-inv-1")
        self.assertEqual(row["source_oa_month"], "2026-03")
        self.assertEqual(row["invoice_bank_relation"], {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"})
        self.assertEqual(row["detail_fields"]["来源OA单号"], "OA-001")
        self.assertEqual(row["summary_fields"]["发票来源"], "OA附件解析")

    def test_build_uses_input_invoice_label_and_oa_id_fallback(self) -> None:
        invoice = SimpleNamespace(
            id="invoice-2",
            invoice_type="input",
            tags=[],
            source_links=[],
            oa_form_id="oa-fallback",
        )
        builder = WorkbenchCanonicalOaAttachmentInvoiceRowBuilder(
            money_text=lambda value: "—",
            first_month_from_oa_row=lambda row: None,
            output_invoice_type_value="output",
        )

        row = builder.build(invoice, source_link={}, oa_row={"id": "oa-row"})

        self.assertEqual(row["invoice_type"], "进项发票")
        self.assertEqual(row["tags"], ["OA附件"])
        self.assertEqual(row["derived_from_oa_id"], "oa-fallback")
        self.assertEqual(row["detail_fields"]["来源OA单号"], "oa-row")


if __name__ == "__main__":
    unittest.main()
