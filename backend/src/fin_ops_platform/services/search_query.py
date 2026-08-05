from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

_MONEY_QUERY_RE = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")


def _money_query_text(value: Any) -> str:
    text = str(value or "").strip()
    return text[1:].strip() if text[:1] in {"¥", "￥"} else text


def is_money_search_query(value: Any) -> bool:
    return _MONEY_QUERY_RE.fullmatch(str(value or "").strip()) is not None


def normalize_money_search_query(value: Any) -> str:
    text = str(value or "").strip()
    return text.replace(",", "") if is_money_search_query(text) else text


def canonicalize_money_search_query(value: Any) -> str:
    text = str(value or "").strip()
    money_text = _money_query_text(text)
    if not _MONEY_QUERY_RE.fullmatch(money_text):
        return text
    try:
        normalized = format(Decimal(money_text.replace(",", "")), "f").rstrip("0").rstrip(".")
    except InvalidOperation:
        return text
    return "0" if normalized in {"", "-0", "+0"} else normalized
