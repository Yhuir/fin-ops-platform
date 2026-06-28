from __future__ import annotations

from io import BytesIO
import unittest

from openpyxl import load_workbook

from fin_ops_platform.services.input_invoice_usage_export_service import (
    INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT,
    InputInvoiceUsageExportError,
    InputInvoiceUsageExportService,
)


class InputInvoiceUsageExportServiceTests(unittest.TestCase):
    def test_export_preview_collects_filtered_rows_and_formats_sample_columns(self) -> None:
        loader = StaticPageLoader(
            [
                self._row("row-1", "inv-1", "3001", "供应商甲", "100.50"),
                self._row("row-2", "inv-2", "3002", "供应商乙", "200.00"),
            ]
        )
        service = InputInvoiceUsageExportService(row_page_loader=loader)

        preview = service.export_preview(
            month="2026-05",
            keyword="供应商",
            filters='[{"field":"seller_name","operator":"contains","value":"供应商"}]',
            sort_field="total_with_tax",
            sort_direction="desc",
        )

        self.assertNotIn("readModelStatus", preview)
        self.assertNotIn("read_model_status", preview)
        self.assertEqual(preview["row_count"], 2)
        self.assertEqual(preview["columns"][0], "序号")
        self.assertEqual(preview["sample_rows"][0]["发票号码"], "3001")
        self.assertEqual(preview["sample_rows"][0]["支付状态"], "未付")
        self.assertEqual(loader.calls[0]["month"], "2026-05")
        self.assertEqual(loader.calls[0]["sort_field"], "total_with_tax")
        self.assertEqual(loader.calls[0]["sort_direction"], "desc")

    def test_export_xlsx_uses_same_rows_and_column_order(self) -> None:
        service = InputInvoiceUsageExportService(
            row_page_loader=StaticPageLoader([self._row("row-1", "inv-1", "3001", "供应商甲", "100.50")])
        )

        filename, content = service.export(month="2026-05")

        self.assertTrue(filename.startswith("进项发票使用情况-"))
        workbook = load_workbook(BytesIO(content), data_only=True)
        sheet = workbook["进项发票使用情况"]
        self.assertEqual(sheet["A1"].value, "序号")
        self.assertEqual(sheet["B1"].value, "行ID")
        self.assertEqual(sheet["C2"].value, "inv-1")
        self.assertEqual(sheet["D2"].value, "3001")
        self.assertEqual(sheet["F2"].value, "供应商甲")
        self.assertEqual(sheet["N2"].value, "未付")

    def test_preview_and_export_do_not_expose_legacy_page_freshness_fields(self) -> None:
        loader = RefreshingPageLoader()
        service = InputInvoiceUsageExportService(row_page_loader=loader)

        preview = service.export_preview(month="2026-05")

        self.assertEqual(preview["row_count"], 0)
        self.assertNotIn("readModelStatus", preview)
        self.assertNotIn("read_model_scope_key", preview)
        filename, content = service.export(month="2026-05")
        self.assertTrue(filename.endswith(".xlsx"))
        self.assertTrue(content)

    def test_row_limit_is_enforced_before_building_workbook(self) -> None:
        service = InputInvoiceUsageExportService(row_page_loader=StaticPageLoader([], total=INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT + 1))

        with self.assertRaises(InputInvoiceUsageExportError) as context:
            service.export(month="2026-05")

        self.assertEqual(context.exception.error_code, "input_invoice_usage_export_row_limit_exceeded")

    def test_loader_unavailable_error_uses_direct_rows_contract(self) -> None:
        service = InputInvoiceUsageExportService(row_page_loader=lambda **_kwargs: None)

        with self.assertRaises(InputInvoiceUsageExportError) as context:
            service.export_preview(month="2026-05")

        self.assertEqual(context.exception.error_code, "input_invoice_usage_export_rows_unavailable")
        self.assertNotIn("read_model", context.exception.error_code)
        self.assertNotIn("读模型", str(context.exception))

    @staticmethod
    def _row(row_id: str, invoice_id: str, invoice_no: str, seller_name: str, total_with_tax: str) -> dict[str, object]:
        return {
            "id": row_id,
            "invoiceId": invoice_id,
            "invoice": {
                "displayNo": invoice_no,
                "invoiceNo": invoice_no,
                "sellerTaxNo": "91530000SELLER",
                "sellerName": seller_name,
                "issueDate": "2026-05-20",
                "specificBusinessType": "现代服务",
                "taxableItemName": "服务费",
                "amountWithoutTax": "94.81",
                "taxRate": "6%",
                "taxAmount": "5.69",
                "totalWithTax": total_with_tax,
            },
            "paymentStatus": {"label": "未付", "reason": "未匹配支付流水"},
            "oa": {
                "primary": {
                    "applicant": "陈秀云",
                    "applicationType": "报销",
                    "projectName": "项目一",
                }
            },
            "bankTransactions": {
                "primary": {
                    "id": "bank-1",
                    "bankName": "中国银行",
                    "tradeTime": "2026-05-21 10:00:00",
                    "amount": "100.50",
                    "directionLabel": "支出",
                    "counterpartyName": seller_name,
                    "summary": "服务费",
                    "remark": "银行备注",
                }
            },
        }


class StaticPageLoader:
    def __init__(self, rows: list[dict[str, object]], *, total: int | None = None) -> None:
        self._rows = rows
        self._total = total
        self.calls: list[dict[str, object]] = []

    def __call__(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        page = int(kwargs.get("page") or 1)
        page_size = int(kwargs.get("page_size") or 500)
        start = (page - 1) * page_size
        page_rows = self._rows[start : start + page_size]
        total = self._total if self._total is not None else len(self._rows)
        return {
            "rows": page_rows,
            "pagination": {"page": page, "pageSize": page_size, "total": total},
        }


class RefreshingPageLoader:
    def __call__(self, **_kwargs: object) -> dict[str, object]:
        return {
            "status": "refreshing",
            "message": "进项发票使用情况正在刷新。",
        }


if __name__ == "__main__":
    unittest.main()
