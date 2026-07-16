from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any
from urllib.parse import unquote


VIEW_MODE_COMPLETED = "completed"
VIEW_MODE_IN_PROGRESS = "in_progress"
VIEW_MODES = {VIEW_MODE_COMPLETED, VIEW_MODE_IN_PROGRESS}

FILTER_CONFIG: dict[str, dict[str, Any]] = {
    "oa_applicant": {"label": "OA申请人", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "oa_application_type": {"label": "类型", "mode": "enum_multi", "operators": {"in", "equals"}, "sortable": True},
    "oa_project_name": {"label": "项目名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "oa_amount": {"label": "金额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "payment_status": {"label": "支付状态", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_trade_time": {"label": "交易时间", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "bank_name": {"label": "支出银行", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_account": {"label": "银行账户", "mode": "enum_multi", "operators": {"in"}, "sortable": False},
    "bank_direction": {"label": "收支", "mode": "enum_multi", "operators": {"in"}, "sortable": False},
    "bank_counterparty_name": {"label": "对方户名", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_summary": {"label": "摘要", "mode": "text", "operators": {"contains"}, "sortable": True},
    "invoice_no": {"label": "数电发票号码", "mode": "text", "operators": {"contains", "equals"}, "sortable": True},
    "seller_name": {"label": "进项发票方名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "invoice_date": {"label": "开票日期", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "invoice_total_with_tax": {"label": "价税合计", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
}
SORT_FIELDS = {field for field, config in FILTER_CONFIG.items() if config["sortable"]}


class OaPendingPaymentError(ValueError):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


def parse_positive_int(value: int | str | None, field: str, *, maximum: int | None = None) -> int:
    try:
        number = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise OaPendingPaymentError("invalid_paging", f"{field} must be a positive integer.") from exc
    if number < 1:
        raise OaPendingPaymentError("invalid_paging", f"{field} must be a positive integer.")
    if maximum is not None and number > maximum:
        raise OaPendingPaymentError("invalid_paging", f"{field} must be <= {maximum}.")
    return number


def parse_filters(filters: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if filters in (None, ""):
        return []
    if isinstance(filters, str):
        try:
            parsed = json.loads(unquote(filters))
        except json.JSONDecodeError as exc:
            raise OaPendingPaymentError("invalid_filter_json", "filters must be a URL-encoded JSON array.") from exc
    else:
        parsed = filters
    if not isinstance(parsed, list):
        raise OaPendingPaymentError("invalid_filter_json", "filters must be a JSON array.")
    normalized = []
    for item in parsed:
        if not isinstance(item, dict):
            raise OaPendingPaymentError("invalid_filter_json", "each filter must be an object.")
        field = str(item.get("field") or "").strip()
        operator = str(item.get("operator") or "").strip()
        if field not in FILTER_CONFIG:
            raise OaPendingPaymentError(
                "invalid_filter_field",
                f"Unsupported filter field: {field}",
                details={"field": field},
            )
        if operator not in FILTER_CONFIG[field]["operators"]:
            raise OaPendingPaymentError(
                "invalid_filter_operator",
                f"Unsupported operator for {field}: {operator}",
                details={"field": field, "operator": operator},
            )
        normalized.append(
            {
                "field": field,
                "operator": operator,
                "value": item.get("value"),
                "values": list(item.get("values") or []),
            }
        )
    return normalized


def parse_view_mode(view_mode: str | None) -> str:
    normalized = str(view_mode or VIEW_MODE_COMPLETED).strip() or VIEW_MODE_COMPLETED
    if normalized not in VIEW_MODES:
        raise OaPendingPaymentError(
            "invalid_view_mode",
            "view_mode must be completed or in_progress.",
            details={"view_mode": normalized},
        )
    return normalized


def parse_sort(sort_field: str | None, sort_direction: str | None) -> tuple[str, str]:
    field = str(sort_field or "bank_trade_time").strip() or "bank_trade_time"
    direction = str(sort_direction or "desc").strip().lower() or "desc"
    if field not in SORT_FIELDS:
        raise OaPendingPaymentError("invalid_sort_field", f"Unsupported sort field: {field}", details={"field": field})
    if direction not in {"asc", "desc"}:
        raise OaPendingPaymentError("invalid_sort_direction", "sort_direction must be asc or desc.")
    return field, direction


def filter_config() -> list[dict[str, Any]]:
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


def option_fields() -> tuple[str, ...]:
    return tuple(field for field, config in FILTER_CONFIG.items() if config["mode"] in {"enum_single", "enum_multi"})
