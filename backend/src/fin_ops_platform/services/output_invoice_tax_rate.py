"""发票税率格式与分组口径；金额比例不属于来源税率。"""
import re
from decimal import Decimal
from typing import Iterable

UNKNOWN_TAX_RATE = "无法确定"
MULTIPLE_TAX_RATES = "多税率"


def normalize_output_tax_rate(value: str | None) -> str:
    text = "" if value is None else str(value).strip()
    if text in {"", "未提供", UNKNOWN_TAX_RATE, "mixed"} or "（推算）" in text:
        return UNKNOWN_TAX_RATE
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%?", text):
        return text
    number = Decimal(text.removesuffix("%"))
    if not text.endswith("%") and number <= 1:
        number *= 100
    formatted = format(number, "f")
    return (formatted.rstrip("0").rstrip(".") if "." in formatted else formatted) + "%"


def normalize_tax_rate_filter_value(value: str | None) -> str:
    """过期筛选保留原值，不能静默扩大为全部未知税率。"""
    text = "" if value is None else str(value).strip()
    if "（推算）" in text or text in {"未提供", "mixed"}:
        return text
    return normalize_output_tax_rate(text)


def combine_invoice_tax_rates(values: Iterable[str | None]) -> str:
    labels = {normalize_output_tax_rate(value) for value in values}
    known = labels - {UNKNOWN_TAX_RATE}
    if MULTIPLE_TAX_RATES in known or len(known) > 1:
        return MULTIPLE_TAX_RATES
    if not known or UNKNOWN_TAX_RATE in labels:
        return UNKNOWN_TAX_RATE
    return next(iter(known))
