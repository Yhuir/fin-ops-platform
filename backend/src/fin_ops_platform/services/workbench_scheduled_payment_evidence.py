from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any


SCHEDULED_PAYMENT_DATE_RE = re.compile(
    r"预约[^，。；;、()（）]{0,20}"
    r"(?:(?P<year>20\d{2})年)?"
    r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日"
    r"[^，。；;、()（）]{0,20}(?:转款|付款|支付|打款)"
)
OA_PAYMENT_TEXT_FIELDS = (
    "reason",
    "purpose",
    "description",
    "summary",
    "payment_reason",
    "payment_purpose",
    "project_name",
    "project",
)
OA_PAYMENT_DETAIL_KEYS = (
    "事由",
    "用途",
    "备注",
    "摘要",
    "申请说明",
    "付款说明",
    "项目名称",
)
BANK_TRADE_DATE_FIELDS = (
    "trade_time",
    "pay_receive_time",
    "transaction_time",
    "transaction_date",
    "trade_date",
    "txn_date",
    "date",
)
BANK_TRADE_DATE_DETAIL_KEYS = (
    "交易时间",
    "支付/收款时间",
    "记账日期",
    "交易日期",
    "日期",
)


def oa_scheduled_payment_date_evidence(
    oa_row: dict[str, Any],
    *,
    owner_month: str | None = None,
) -> dict[str, Any] | None:
    resolved_owner_month = _owner_month(oa_row, owner_month)
    fallback_year = _year_from_month(resolved_owner_month)
    for source_field, text in _oa_scheduled_payment_text_values(oa_row):
        match = SCHEDULED_PAYMENT_DATE_RE.search(text)
        if match is None:
            continue
        year = int(match.group("year")) if match.group("year") else fallback_year
        if year is None:
            continue
        try:
            scheduled_date = date(year, int(match.group("month")), int(match.group("day")))
        except ValueError:
            continue
        return {
            "scheduled_payment_date": scheduled_date.isoformat(),
            "source_field": source_field,
            "source_text": text,
        }
    return None


def bank_explicit_trade_date(bank_row: dict[str, Any]) -> date | None:
    for _source_field, value in _bank_trade_date_values(bank_row):
        parsed = _parse_explicit_date(value)
        if parsed is not None:
            return parsed
    return None


def scheduled_payment_date_match(
    oa_row: dict[str, Any],
    bank_row: dict[str, Any],
    *,
    owner_month: str | None = None,
) -> dict[str, Any] | None:
    scheduled = oa_scheduled_payment_date_evidence(oa_row, owner_month=owner_month)
    if scheduled is None:
        return None
    bank_date = bank_explicit_trade_date(bank_row)
    if bank_date is None or bank_date.isoformat() != scheduled["scheduled_payment_date"]:
        return None
    return {
        **scheduled,
        "bank_trade_date": bank_date.isoformat(),
    }


def scheduled_payment_date_compatible(
    oa_row: dict[str, Any],
    bank_row: dict[str, Any],
    *,
    owner_month: str | None = None,
) -> bool:
    scheduled = oa_scheduled_payment_date_evidence(oa_row, owner_month=owner_month)
    if scheduled is None:
        return True
    bank_date = bank_explicit_trade_date(bank_row)
    return bank_date is not None and bank_date.isoformat() == scheduled["scheduled_payment_date"]


def _owner_month(row: dict[str, Any], explicit_owner_month: str | None) -> str:
    for value in (
        explicit_owner_month,
        row.get("month"),
        row.get("scope_month"),
        row.get("application_month"),
    ):
        text = str(value or "").strip()
        if len(text) >= 7:
            return text[:7]
    return ""


def _year_from_month(month: str) -> int | None:
    if len(month) < 4:
        return None
    try:
        return int(month[:4])
    except ValueError:
        return None


def _oa_scheduled_payment_text_values(row: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for field_name in OA_PAYMENT_TEXT_FIELDS:
        values.extend((field_name, value) for value in _flatten_text_values(row.get(field_name)))
    for detail_key in ("detail_fields", "_detail_fields"):
        detail_fields = row.get(detail_key)
        if not isinstance(detail_fields, dict):
            continue
        for field_name in OA_PAYMENT_DETAIL_KEYS:
            values.extend(
                (f"{detail_key}.{field_name}", value)
                for value in _flatten_text_values(detail_fields.get(field_name))
            )
    return values


def _bank_trade_date_values(row: dict[str, Any]) -> list[tuple[str, Any]]:
    values: list[tuple[str, Any]] = [(field_name, row.get(field_name)) for field_name in BANK_TRADE_DATE_FIELDS]
    for detail_key in ("detail_fields", "_detail_fields"):
        detail_fields = row.get(detail_key)
        if not isinstance(detail_fields, dict):
            continue
        values.extend(
            (f"{detail_key}.{field_name}", detail_fields.get(field_name))
            for field_name in BANK_TRADE_DATE_DETAIL_KEYS
        )
    return values


def _flatten_text_values(value: Any) -> list[str]:
    if value in (None, "", "--", "—"):
        return []
    if isinstance(value, dict):
        values: list[str] = []
        for nested_value in value.values():
            values.extend(_flatten_text_values(nested_value))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_flatten_text_values(item))
        return values
    text = str(value).strip()
    return [text] if text else []


def _parse_explicit_date(value: Any) -> date | None:
    if value in (None, "", "--", "—"):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    match = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if match is None:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None
