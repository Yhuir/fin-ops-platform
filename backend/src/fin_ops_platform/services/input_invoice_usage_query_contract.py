from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote


class InputInvoiceUsageQueryContractError(ValueError):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


FILTER_CONFIG: dict[str, dict[str, Any]] = {
    "invoice_no": {"label": "发票号码", "mode": "text", "operators": {"contains", "equals"}, "sortable": True},
    "invoice_date": {"label": "开票日期", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "seller_name": {"label": "销方名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "seller_tax_no": {"label": "销方识别号", "mode": "text", "operators": {"contains", "equals"}, "sortable": True},
    "total_with_tax": {"label": "价税合计", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "amount": {"label": "不含税金额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "tax_rate": {"label": "税率", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "tax_amount": {"label": "税额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "specific_business_type": {"label": "特定业务类型", "mode": "enum_multi", "operators": {"in"}, "sortable": False},
    "taxable_item_name": {"label": "货物或应税劳务名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "payment_status": {"label": "支付状态", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "oa_applicant": {"label": "OA申请人", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "oa_application_type": {"label": "报销/支付", "mode": "enum_multi", "operators": {"in", "equals"}, "sortable": True},
    "oa_project_name": {"label": "项目名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_counterparty_name": {"label": "对方户名", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_trade_time": {"label": "交易时间", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "bank_amount": {"label": "流水金额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "bank_name": {"label": "支付银行", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_account": {"label": "银行账户", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_direction": {"label": "收支", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_summary": {"label": "摘要", "mode": "text", "operators": {"contains"}, "sortable": True},
}

SORT_FIELDS = {field for field, config in FILTER_CONFIG.items() if config["sortable"]}


def input_invoice_usage_filter_config() -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "label": config["label"],
            "mode": config["mode"],
            "operators": sorted(config["operators"]),
            "sortable": bool(config["sortable"]),
        }
        for field, config in FILTER_CONFIG.items()
    ]


def parse_input_invoice_usage_filters(filters: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if filters in (None, ""):
        return []
    if isinstance(filters, str):
        try:
            parsed = json.loads(unquote(filters))
        except json.JSONDecodeError as exc:
            raise InputInvoiceUsageQueryContractError(
                "invalid_filter_json",
                "filters must be a URL-encoded JSON array.",
            ) from exc
    else:
        parsed = filters
    if not isinstance(parsed, list):
        raise InputInvoiceUsageQueryContractError("invalid_filter_json", "filters must be a JSON array.")
    normalized = []
    for item in parsed:
        if not isinstance(item, dict):
            raise InputInvoiceUsageQueryContractError("invalid_filter_json", "each filter must be an object.")
        field = str(item.get("field") or "").strip()
        operator = str(item.get("operator") or "").strip()
        if field not in FILTER_CONFIG:
            raise InputInvoiceUsageQueryContractError(
                "invalid_filter_field",
                f"Unsupported filter field: {field}",
                details={"field": field},
            )
        if operator not in FILTER_CONFIG[field]["operators"]:
            raise InputInvoiceUsageQueryContractError(
                "invalid_filter_operator",
                f"Unsupported operator for {field}: {operator}",
                details={"field": field, "operator": operator},
            )
        normalized.append({"field": field, "operator": operator, "value": item.get("value"), "values": list(item.get("values") or [])})
    return normalized


def parse_input_invoice_usage_sort(sort_field: object, sort_direction: object) -> tuple[str, str]:
    field = str(sort_field or "invoice_date").strip() or "invoice_date"
    direction = str(sort_direction or "desc").strip().lower() or "desc"
    if field not in SORT_FIELDS:
        raise InputInvoiceUsageQueryContractError(
            "invalid_sort_field",
            f"Unsupported sort field: {field}",
            details={"field": field},
        )
    if direction not in {"asc", "desc"}:
        raise InputInvoiceUsageQueryContractError("invalid_sort_direction", "sort_direction must be asc or desc.")
    return field, direction
