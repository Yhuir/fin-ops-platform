from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Any, Callable

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT = 20000
INPUT_INVOICE_USAGE_EXPORT_COLUMNS = [
    "序号", "发票号码", "发票代码", "销方识别号", "销方名称", "开票日期",
    "特定业务类型", "货物或应税劳务名称", "不含税金额", "税率", "税额", "价税合计",
]


class InputInvoiceUsageExportError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class InputInvoiceUsageExportService:
    def __init__(self, *, row_export_loader: Callable[..., dict[str, Any]]) -> None:
        self._row_export_loader = row_export_loader

    def export_summary(self, **query: Any) -> dict[str, Any]:
        payload = self._row_export_loader(limit=0, **query)
        return {"row_count": payload["total"], "filter_options": payload["filterOptions"]}

    def export(self, *, today: date | None = None, **query: Any) -> tuple[str, bytes]:
        payload = self._row_export_loader(limit=INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT + 1, **query)
        if payload["total"] > INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT:
            raise InputInvoiceUsageExportError(
                "input_invoice_usage_export_row_limit_exceeded",
                f"导出超过 {INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT} 张，请缩小筛选范围。",
            )
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("进项发票")
        sheet.append(INPUT_INVOICE_USAGE_EXPORT_COLUMNS)
        for index, row in enumerate(payload["rows"], 1):
            values = self._formal_row(index, row)
            cells = []
            for value in values:
                cell = WriteOnlyCell(sheet, value=value)
                if isinstance(value, str):
                    cell.data_type = "s"
                cells.append(cell)
            sheet.append(cells)
        buffer = BytesIO()
        workbook.save(buffer)
        return f"进项发票-{(today or date.today()).isoformat()}.xlsx", buffer.getvalue()

    @staticmethod
    def _formal_row(index: int, row: dict[str, Any]) -> list[Any]:
        invoice = row["invoice"]
        return [index, invoice["invoiceNo"], invoice["invoiceCode"], invoice["sellerTaxNo"],
                invoice["sellerName"], invoice["invoiceDate"], invoice["specificBusinessType"],
                invoice["taxableItemName"], Decimal(invoice["amount"]) if invoice["amount"] else None, invoice["taxRate"],
                Decimal(invoice["taxAmount"]) if invoice["taxAmount"] else invoice.get("taxAmountText"),
                Decimal(invoice["totalWithTax"]) if invoice["totalWithTax"] else None]
