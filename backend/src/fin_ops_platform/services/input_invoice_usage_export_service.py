from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import Any, Callable

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font


INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT = 20000
INPUT_INVOICE_USAGE_EXPORT_PAGE_SIZE = 200
INPUT_INVOICE_USAGE_EXPORT_COLUMNS = [
    "序号",
    "行ID",
    "发票ID",
    "发票号码",
    "销方识别号",
    "销方名称",
    "开票日期",
    "特定业务类型",
    "货物或应税劳务名称",
    "不含税金额",
    "税率",
    "税额",
    "价税合计",
    "支付状态",
    "支付状态原因",
    "OA申请人",
    "报销/支付",
    "项目名称",
    "支付银行",
    "交易时间",
    "流水金额",
    "收支方向",
    "对方户名",
    "摘要",
    "银行备注",
]


class InputInvoiceUsageExportError(ValueError):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        refresh_payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.refresh_payload = refresh_payload


class InputInvoiceUsageExportService:
    def __init__(self, *, row_page_loader: Callable[..., dict[str, Any] | None]) -> None:
        self._row_page_loader = row_page_loader

    def export_preview(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        today: date | None = None,
    ) -> dict[str, Any]:
        collection = self._collect_rows(
            month=month,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            allow_refreshing=True,
        )
        if collection.get("refreshing"):
            return self._refreshing_preview(collection["refresh_payload"])
        rows = [self._formal_row(index, row) for index, row in enumerate(collection["rows"], start=1)]
        return {
            "file_name": self._filename(today=today),
            "row_count": len(rows),
            "scope_label": "当前筛选",
            "columns": list(INPUT_INVOICE_USAGE_EXPORT_COLUMNS),
            "sample_rows": rows[:20],
            "rows": rows[:20],
            "pagination": {"preview_count": min(len(rows), 20), "total": len(rows), "limit": 20},
            "readModelStatus": "fresh",
            "read_model_status": "fresh",
            "read_model_scope_key": collection.get("read_model_scope_key") or "",
        }

    def export(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        today: date | None = None,
    ) -> tuple[str, bytes]:
        collection = self._collect_rows(
            month=month,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            allow_refreshing=False,
        )
        rows = [self._formal_row(index, row) for index, row in enumerate(collection["rows"], start=1)]
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "进项发票使用情况"
        sheet.append(INPUT_INVOICE_USAGE_EXPORT_COLUMNS)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        for row in rows:
            sheet.append([row.get(column, "") for column in INPUT_INVOICE_USAGE_EXPORT_COLUMNS])
        for column_cells in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 36)
        buffer = BytesIO()
        workbook.save(buffer)
        return self._filename(today=today), buffer.getvalue()

    def _collect_rows(
        self,
        *,
        month: str | None,
        keyword: str | None,
        invoice_date_from: str | None,
        invoice_date_to: str | None,
        filters: str | list[dict[str, Any]] | None,
        sort_field: str | None,
        sort_direction: str | None,
        allow_refreshing: bool,
    ) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        page = 1
        total: int | None = None
        read_model_scope_key = ""
        while total is None or len(rows) < total:
            payload = self._row_page_loader(
                month=month,
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                filters=filters,
                sort_field=sort_field or "invoice_date",
                sort_direction=sort_direction or "desc",
                page=page,
                page_size=INPUT_INVOICE_USAGE_EXPORT_PAGE_SIZE,
                include_statistics=page == 1,
            )
            if not isinstance(payload, dict):
                raise InputInvoiceUsageExportError(
                    "input_invoice_usage_export_read_model_unavailable",
                    "进项发票使用情况读模型不可用，请先刷新读模型。",
                )
            status = self._read_model_status(payload)
            if status != "fresh":
                refresh_payload = self._normalize_refresh_payload(payload)
                if allow_refreshing:
                    return {"refreshing": True, "refresh_payload": refresh_payload}
                raise InputInvoiceUsageExportError(
                    "input_invoice_usage_export_read_model_refreshing",
                    "进项发票使用情况读模型正在刷新，请稍后再导出。",
                    refresh_payload=refresh_payload,
                )
            read_model_scope_key = self._text(payload.get("read_model_scope_key") or payload.get("readModelScopeKey"))
            pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
            total = self._int(pagination.get("total"), len(payload.get("rows") or []))
            if total > INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT:
                raise InputInvoiceUsageExportError(
                    "input_invoice_usage_export_row_limit_exceeded",
                    f"当前筛选命中 {total} 行，超过 {INPUT_INVOICE_USAGE_EXPORT_ROW_LIMIT} 行导出上限，请缩小筛选范围。",
                )
            page_rows = [dict(row) for row in list(payload.get("rows") or []) if isinstance(row, dict)]
            rows.extend(page_rows)
            if not page_rows:
                break
            page += 1
        return {
            "rows": rows[: total or len(rows)],
            "read_model_scope_key": read_model_scope_key,
            "refreshing": False,
        }

    @classmethod
    def _formal_row(cls, index: int, row: dict[str, Any]) -> dict[str, Any]:
        invoice = row.get("invoice") if isinstance(row.get("invoice"), dict) else {}
        payment_status = cls._mapping(row.get("paymentStatus") or row.get("payment_status"))
        oa_relation = cls._mapping(row.get("oa"))
        oa_primary = cls._mapping(oa_relation.get("primary") or oa_relation)
        bank_relation = cls._mapping(row.get("bankTransactions") or row.get("bank") or row.get("bank_transactions"))
        bank_primary = cls._mapping(bank_relation.get("primary") or bank_relation)
        return {
            "序号": index,
            "行ID": cls._text(row.get("id")),
            "发票ID": cls._text(row.get("invoiceId") or row.get("invoice_id") or invoice.get("id")),
            "发票号码": cls._text(invoice.get("displayNo") or invoice.get("display_no") or invoice.get("invoiceNo") or invoice.get("invoice_no")),
            "销方识别号": cls._text(invoice.get("sellerTaxNo") or invoice.get("seller_tax_no")),
            "销方名称": cls._text(invoice.get("sellerName") or invoice.get("seller_name")),
            "开票日期": cls._text(invoice.get("issueDate") or invoice.get("issue_date") or invoice.get("invoiceDate") or invoice.get("invoice_date")),
            "特定业务类型": cls._text(invoice.get("specificBusinessType") or invoice.get("specific_business_type")),
            "货物或应税劳务名称": cls._text(invoice.get("taxableItemName") or invoice.get("taxable_item_name")),
            "不含税金额": cls._text(invoice.get("amountWithoutTax") or invoice.get("amount_without_tax") or invoice.get("amount")),
            "税率": cls._text(invoice.get("taxRate") or invoice.get("tax_rate")),
            "税额": cls._text(invoice.get("taxAmount") or invoice.get("tax_amount")),
            "价税合计": cls._text(invoice.get("totalWithTax") or invoice.get("total_with_tax")),
            "支付状态": cls._text(payment_status.get("label")),
            "支付状态原因": cls._text(payment_status.get("reason")),
            "OA申请人": cls._text(oa_primary.get("applicant") or oa_primary.get("applicantName") or oa_primary.get("applicant_name")),
            "报销/支付": cls._text(oa_primary.get("applicationType") or oa_primary.get("application_type") or oa_primary.get("applyType") or oa_primary.get("apply_type")),
            "项目名称": cls._text(oa_primary.get("projectName") or oa_primary.get("project_name")),
            "支付银行": cls._text(bank_primary.get("bankName") or bank_primary.get("bank_name")),
            "交易时间": cls._text(bank_primary.get("tradeTime") or bank_primary.get("trade_time")),
            "流水金额": cls._text(bank_primary.get("amount")),
            "收支方向": cls._text(bank_primary.get("directionLabel") or bank_primary.get("direction_label") or bank_primary.get("direction")),
            "对方户名": cls._text(bank_primary.get("counterpartyName") or bank_primary.get("counterparty_name")),
            "摘要": cls._text(bank_primary.get("summary")),
            "银行备注": cls._text(bank_primary.get("remark")),
        }

    @staticmethod
    def _filename(*, today: date | None = None) -> str:
        return f"进项发票使用情况-{(today or date.today()).isoformat()}.xlsx"

    @classmethod
    def _normalize_refresh_payload(cls, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        normalized["readModelStatus"] = "refreshing"
        normalized["read_model_status"] = "refreshing"
        normalized.setdefault("row_count", 0)
        normalized.setdefault("columns", list(INPUT_INVOICE_USAGE_EXPORT_COLUMNS))
        normalized.setdefault("sample_rows", [])
        normalized.setdefault("message", "进项发票使用情况读模型正在刷新，请稍后再试。")
        return normalized

    @classmethod
    def _refreshing_preview(cls, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = cls._normalize_refresh_payload(payload)
        normalized.setdefault("file_name", cls._filename())
        normalized.setdefault("scope_label", "当前筛选")
        return normalized

    @classmethod
    def _read_model_status(cls, payload: dict[str, Any]) -> str:
        status = cls._text(payload.get("read_model_status") or payload.get("readModelStatus") or payload.get("status"))
        return status or "fresh"

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _text(value: Any) -> str:
        return "" if value is None else str(value)

    @staticmethod
    def _int(value: Any, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
