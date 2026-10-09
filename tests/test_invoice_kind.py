import unittest

from fin_ops_platform.services.invoice_kind import extract_invoice_kind, invoice_kind_fields


class InvoiceKindTests(unittest.TestCase):
    def test_source_aliases_and_unicode_preserve_original(self):
        for text in ("数电发票（增值税专用发票）", "电⼦发票（增值税专用发票）"):
            result = invoice_kind_fields(text)
            self.assertEqual(result["invoice_kind"], text)
            self.assertEqual(result["invoice_kind_code"], "vat_special")
            self.assertEqual(result["invoice_kind_status"], "confirmed")

    def test_absence_and_unknown_are_distinct_without_guessing(self):
        self.assertEqual(invoice_kind_fields(None)["invoice_kind_status"], "not_provided")
        self.assertEqual(
            invoice_kind_fields(None, missing_status="source_unavailable")["invoice_kind_status"], "source_unavailable"
        )
        for text in ("电子发票", "ETC发票", "电子发票增值税专用发票）", "13%"):
            result = invoice_kind_fields(text)
            self.assertIsNone(result["invoice_kind_code"])
            self.assertEqual(result["invoice_kind_status"], "unmapped")

    def test_title_extraction_excludes_product_code_and_remarks(self):
        for text in ("发票代码：1234", "*文具*发票封面 13%", "备注：增值税专用发票"):
            self.assertIsNone(extract_invoice_kind(text))
        text = "电子发票（铁路电子客票）"
        self.assertEqual(extract_invoice_kind(text), text)
        self.assertEqual(invoice_kind_fields("云南通用机打发票")["invoice_kind_code"], "machine_invoice")
