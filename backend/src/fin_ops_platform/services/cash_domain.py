"""Strict cash value types and pure accounting checks; no HTTP or persistence I/O."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo


class CashError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def invalid(message: str) -> None:
    raise CashError("cash_invalid_input", message)


def conflict(message: str, code: str = "cash_allocation_conflict") -> None:
    raise CashError(code, message, 409)


def shanghai_today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def fields(value: Any, allowed: set[str], required: set[str] = frozenset()) -> dict:
    if not isinstance(value, dict):
        invalid("请求必须是对象。")
    if set(value) - allowed:
        invalid("存在不允许的字段：" + ", ".join(sorted(set(value) - allowed)))
    if required - set(value):
        invalid("缺少必填字段：" + ", ".join(sorted(required - set(value))))
    return dict(value)


def normalize_uuid(value: Any, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        invalid("ID 必须是 UUID 字符串。")
    try:
        return str(UUID(value))
    except ValueError:
        invalid("ID 不是有效 UUID。")


def normalize_money(value: Any, *, signed: bool = False, allow_zero: bool = False) -> Decimal:
    if not isinstance(value, str) or len(value) > 20 or not re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d{1,2})?", value):
        invalid("金额须为人民币两位以内的十进制字符串。")
    amount = Decimal(value)
    if not amount.is_finite() or abs(amount) > Decimal("9999999999999999.99"):
        invalid("金额超出允许范围。")
    if not signed and (amount < 0 or (amount == 0 and not allow_zero)):
        invalid("金额必须大于零。")
    return amount.quantize(Decimal("0.01"))


def normalize_date(value: Any, *, nullable: bool = False) -> date | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        invalid("日期须为 YYYY-MM-DD。")
    try:
        return date.fromisoformat(value)
    except ValueError:
        invalid("日期无效。")


def normalize_text(value: Any, *, maximum: int = 120, nullable: bool = False) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        invalid("文本字段类型错误。")
    value = value.strip()
    if not value and nullable:
        return None
    if not value or len(value) > maximum:
        invalid(f"文本长度须为 1 至 {maximum} 个字符。")
    return value


def normalize_version(value: Any, nullable: bool = False) -> int | None:
    if value is None and nullable:
        return None
    if type(value) is not int or not 1 <= value <= 2147483647:
        invalid("预期版本必须是正整数。")
    return value


def normalize_bool(value: Any) -> bool:
    if type(value) is not bool:
        invalid("布尔字段必须为 true 或 false。")
    return value


def enum(value: Any, choices: set[str]) -> str:
    if not isinstance(value, str) or value not in choices:
        invalid("字段选项无效。")
    return value


def check_version(row: dict, expected: Any) -> None:
    if row["version"] != normalize_version(expected):
        conflict("数据已经变化，请刷新后重新确认。", "cash_version_conflict")


def serialize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, ".2f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(item) for item in value]
    return value


def exact_sum(values) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 60
        return sum(values, Decimal("0.00"))


CASH_SETTLEMENTS = frozenset({"cash_repayment", "company_collection", "expense_payment", "expense_refund"})
SETTLEMENT_KINDS = CASH_SETTLEMENTS | {"ticket_use", "ticket_offset", "non_ticket_offset"}


def item_amounts(item: dict, settlements: list[dict]) -> dict:
    def total(kinds, column="item_id"):
        return exact_sum(s["amount"] for s in settlements if s[column] == item["id"] and s["kind"] in kinds)
    original = item["original_amount"]
    if item["type"] in {"loan", "company_receivable"}:
        cash = total({"cash_repayment", "company_collection"})
        ticket = total({"ticket_offset"})
        non_ticket = total({"non_ticket_offset"})
        return {"original_amount": original, "cash_settled_amount": cash, "ticket_offset_amount": ticket,
                "non_ticket_offset_amount": non_ticket, "remaining_obligation_amount": original - cash - ticket - non_ticket}
    if item["type"] == "expense":
        paid = total({"expense_payment"}) + (original if item["origin_flow_id"] else Decimal(0))
        refund = total({"expense_refund"})
        offset = total({"non_ticket_offset"}, "source_item_id")
        return {"original_amount": original, "paid_amount": paid, "refund_amount": refund,
                "net_expense_amount": original-refund, "available_offset_amount": original-refund-offset}
    used = total({"ticket_use", "ticket_offset"}, "source_item_id")
    return {"provided_amount": original, "used_amount": used,
            "offset_amount": total({"ticket_offset"}, "source_item_id"), "available_source_amount": original-used}


def validate_item_amounts(item: dict, settlements: list[dict]) -> None:
    amounts = item_amounts(item, settlements)
    if item["type"] in {"loan", "company_receivable"}:
        if amounts["remaining_obligation_amount"] < 0:
            conflict("结算金额超过事项原额。")
    elif item["type"] == "expense":
        if amounts["paid_amount"] > item["original_amount"]:
            conflict("费用付款超过原费用金额。")
        if amounts["refund_amount"] > min(amounts["paid_amount"], item["original_amount"]):
            conflict("费用退款超过真实已支付金额。")
        if amounts["available_offset_amount"] < 0:
            conflict("无票冲抵超过费用净额。")
    elif amounts["available_source_amount"] < 0:
        conflict("票据使用超过来源金额。")
