from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.pending_invoice_rules import (
    PENDING_INVOICE_CASH_INCOME_GROUP,
    PENDING_INVOICE_NO_INVOICE_GROUP,
)

EXPENSE_REQUIRES_INVOICE_STATUS_CODES = (
    "paid_invoiced",
    "paid_pending_invoice",
    "paid_pending_future_invoice",
    "invoice_not_fully_paid",
)
INCOME_REQUIRES_INVOICE_STATUS_CODES = ("income_pending_invoice", "income_invoiced")
PENDING_INVOICE_FILTER_STATUS_CODES: dict[str, dict[str, tuple[str, ...]]] = {
    "expense": {
        "requires_invoice": EXPENSE_REQUIRES_INVOICE_STATUS_CODES,
        "bank_statement_as_invoice": ("bank_statement_as_invoice",),
        "no_invoice_required": ("no_invoice_required",),
    },
    "income": {
        "requires_invoice": INCOME_REQUIRES_INVOICE_STATUS_CODES,
        "no_invoice_required": ("income_no_invoice_required",),
        "cash_income": ("cash_income",),
    },
}


def pending_invoice_status_payload(
    *,
    direction: str,
    group: str | None,
    has_invoices: bool,
    payment_summary: dict[str, Any],
    matched_rule: dict[str, Any] | None,
    status_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if direction == "income":
        if has_invoices:
            return _status(
                "income_invoiced",
                "已开票",
                "收入流水已关联销项发票。",
                "success",
                "view_relation",
                matched_rule,
            )
        if isinstance(status_override, dict):
            status_code = str(status_override.get("status_code") or "").strip()
            if status_code == "income_no_invoice_required":
                return _status("income_no_invoice_required", "无需开票", "收入流水已人工标记为无需开票。", "default", "none", matched_rule)
            if status_code == "cash_income":
                return _status("cash_income", "现金收入", "收入流水已人工标记为现金收入。", "info", "none", matched_rule)
        if group == PENDING_INVOICE_NO_INVOICE_GROUP:
            return _status("income_no_invoice_required", "无需开票", "收入流水分类命中无需开票规则。", "default", "view_rules", matched_rule)
        if group == PENDING_INVOICE_CASH_INCOME_GROUP:
            return _status("cash_income", "现金收入", "收入流水分类命中现金收入规则。", "info", "view_rules", matched_rule)
        return _status(
            "income_pending_invoice",
            "未开票",
            "收入流水未关联销项发票，也未命中无需开票或现金收入规则。",
            "error",
            "mark_income_status",
            matched_rule,
        )

    invoice_total = _decimal_from_text(payment_summary.get("invoice_total"))
    paid_total = _decimal_from_text(payment_summary.get("paid_total"))
    if has_invoices and invoice_total > paid_total:
        return _status(
            "invoice_not_fully_paid",
            "未支付完已开票",
            "已有关联进项发票，但关联支付流水合计小于发票价税合计。",
            "warning",
            "view_relation",
            matched_rule,
        )
    if has_invoices:
        return _status("paid_invoiced", "已支付已开票", "支出流水已关联进项发票。", "success", "view_relation", matched_rule)
    if group == PENDING_INVOICE_NO_INVOICE_GROUP:
        return _status("no_invoice_required", "无需开票", "流水分类命中无需开票规则。", "default", "view_rules", matched_rule)
    if group == "bank_statement_as_invoice":
        return _status("bank_statement_as_invoice", "流水代替发票", "流水分类命中流水代替发票规则。", "info", "view_rules", matched_rule)
    return _status(
        "paid_pending_invoice",
        "已支付待开票",
        "支出流水未关联进项发票，也未命中免票或流水替票规则。",
        "error",
        "attach_or_create_invoice",
        matched_rule,
    )


def pending_invoice_available_actions(status_payload: dict[str, Any], *, can_create_invoice: bool) -> list[str]:
    action = str(status_payload.get("primary_action") or "").strip()
    if action == "attach_or_create_invoice":
        return ["attach_existing_invoice"] if can_create_invoice else []
    if action == "mark_income_status":
        return ["mark_income_status"]
    if action in {"view_relation", "view_rules"}:
        return [action]
    return []


def pending_invoice_filter_status_codes(*, direction: str, filter_name: str) -> tuple[str, ...]:
    normalized_direction = str(direction or "").strip() or "expense"
    normalized_filter = str(filter_name or "").strip() or "all"
    return PENDING_INVOICE_FILTER_STATUS_CODES.get(normalized_direction, {}).get(normalized_filter, ())


def pending_invoice_status_matches_filter(*, direction: str, filter_name: str, status_code: str) -> bool:
    status_codes = pending_invoice_filter_status_codes(direction=direction, filter_name=filter_name)
    return True if not status_codes else str(status_code or "").strip() in status_codes


def _status(
    code: str,
    label: str,
    reason: str,
    severity: str,
    primary_action: str,
    matched_rule: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "reason": reason,
        "severity": severity,
        "primary_action": primary_action,
        "matched_rule": matched_rule,
    }


def _decimal_from_text(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0.00")
