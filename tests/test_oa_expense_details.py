import unittest

from fin_ops_platform.services.oa_expense_details import (
    oa_expense_detail_sections,
    oa_expense_source_metadata,
    public_oa_expense_items,
)


class OaExpenseDetailsTests(unittest.TestCase):
    def test_public_projection_preserves_duplicate_rows_zero_and_missing_fields(self):
        item = {"expense_content": "交通费", "amount": "0.00", "ticket_count": 0,
                "expense_item_id": "private-id", "attachment_files": [{"url": "private-url"}]}
        public = public_oa_expense_items([item, item])
        self.assertEqual(public, [{"expense_content": "交通费", "amount": "0.00", "ticket_count": 0}] * 2)
        sections = oa_expense_detail_sections(public)
        self.assertEqual([section["title"] for section in sections], ["费用明细 1", "费用明细 2"])
        fields = {field["label"]: field["value"] for field in sections[0]["fields"]}
        self.assertEqual(fields["票据张数"], "0")
        self.assertEqual(fields["支付方式"], "—")
        self.assertEqual(oa_expense_detail_sections([]), [])

    def test_source_enum_labels_and_unknown_codes_are_not_inferred(self):
        self.assertEqual(oa_expense_source_metadata({"detailPaymentMethod": "WeChat_pay",
            "detailTypeOfInvoice": "Special_invoice", "detailNumberOfBills": 0}),
            {"payment_method": "微信支付", "invoice_kind": "普通发票/行政收据", "ticket_count": "0"})
        self.assertEqual(oa_expense_source_metadata({"detailPaymentMethod": "new-code"}),
            {"payment_method": "new-code", "invoice_kind": "", "ticket_count": ""})
