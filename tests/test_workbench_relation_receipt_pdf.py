from __future__ import annotations

import unittest

import fitz

from fin_ops_platform.services.workbench_relation_receipt_pdf import (
    WorkbenchReceiptPdfRenderer,
    _uppercase_rmb,
)


class WorkbenchRelationReceiptPdfTests(unittest.TestCase):
    def test_uppercase_rmb_formats_money_boundaries(self) -> None:
        self.assertEqual(_uppercase_rmb("0"), "人民币 零元整")
        self.assertEqual(_uppercase_rmb("1001.05"), "人民币 壹仟零壹元零伍分")
        self.assertEqual(_uppercase_rmb("100010001.10"), "人民币 壹亿零壹万零壹元壹角")

    def test_renderer_creates_one_template_copy_and_continuation_pages_without_dropping_lines(self) -> None:
        lines = [
            {
                "summary": f"技术服务费 {index}",
                "amount": f"{index}.00",
                "note": f"备注 {index}",
            }
            for index in range(1, 7)
        ]
        content = WorkbenchReceiptPdfRenderer().render({
            "case_id": "CASE-PDF-1",
            "total_amount": "600.00",
            "receipts": [{
                "payer": "成都智领趋势科技有限公司",
                "date": "2026-08-28",
                "currency": "CNY",
                "amount": "600.00",
                "handler": "",
                "supervisor": "",
                "bank_transaction_ids": ["bank-1"],
                "lines": lines,
            }],
        })

        document = fitz.open(stream=content, filetype="pdf")
        try:
            self.assertEqual(document.page_count, 2)
            for page in document:
                self.assertAlmostEqual(page.rect.width, 595.28, places=1)
                self.assertAlmostEqual(page.rect.height, 419.53, places=1)
            all_text = "\n".join(page.get_text() for page in document)
        finally:
            document.close()

        self.assertIn("云南溯源科技有限公司", all_text)
        self.assertIn("收    据", all_text)
        self.assertIn("成都智领趋势科技有限公司", all_text)
        self.assertIn("人民币", all_text)
        self.assertIn("陆佰元整", all_text)
        self.assertNotIn("收款人留存", all_text)
        self.assertNotIn("付款人留存", all_text)
        for line in lines:
            self.assertEqual(all_text.count(line["summary"]), 1)


if __name__ == "__main__":
    unittest.main()
