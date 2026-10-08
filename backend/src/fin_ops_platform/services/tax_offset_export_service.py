from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell

from fin_ops_platform.services.tax_offset_query_service import (
    DEFAULT_EXPORT_FIELDS,
    TAX_OFFSET_EXPORT_FIELDS,
    TaxOffsetQueryService,
)

# Match the existing financial invoice XLSX export resource limit.
TAX_OFFSET_EXPORT_ROW_LIMIT = 20000


class TaxOffsetExportError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class TaxOffsetExportService:
    def __init__(self, *, query_service: TaxOffsetQueryService) -> None:
        self._query_service = query_service

    def export(self, filters: dict[str, object], fields: list[str] | None = None) -> tuple[str, bytes]:
        selected = list(DEFAULT_EXPORT_FIELDS) if fields is None else fields
        catalog = dict(TAX_OFFSET_EXPORT_FIELDS)
        if (not isinstance(selected, list) or not selected or not all(isinstance(key, str) for key in selected)
                or len(selected) != len(set(selected)) or any(key not in catalog for key in selected)):
            raise TaxOffsetExportError("invalid_tax_offset_export_fields", "请选择有效且不重复的导出字段。")
        payload = self._query_service.export_rows(filters, limit=TAX_OFFSET_EXPORT_ROW_LIMIT + 1)
        if payload["total"] > TAX_OFFSET_EXPORT_ROW_LIMIT:
            raise TaxOffsetExportError("tax_offset_export_row_limit_exceeded", "导出超过 20000 张，请缩小筛选范围。")
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet("专票清单")
        sheet.append([catalog[key] for key in selected])
        for row in payload["rows"]:
            cells = []
            for key in selected:
                value = _export_value(row, key)
                cell = WriteOnlyCell(sheet, value=value)
                if isinstance(value, str):
                    cell.data_type = "s"
                if key in ("amount", "tax_amount", "deductible_tax_amount"):
                    cell.number_format = "0.00######"
                cells.append(cell)
            sheet.append(cells)
        buffer = BytesIO()
        workbook.save(buffer)
        day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        return f"专票清单-{day}.xlsx", buffer.getvalue()


def _export_value(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    if key == "certification_status":
        return {"certified": "已认证", "uncertified": "未认证"}[value]
    if key in ("amount", "tax_amount", "deductible_tax_amount"):
        return Decimal(value) if value is not None else None
    return value
