from __future__ import annotations

import re
from typing import Any


_MONEY_QUERY_RE = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")


def is_money_search_query(value: Any) -> bool:
    return _MONEY_QUERY_RE.fullmatch(str(value or "").strip()) is not None


def normalize_money_search_query(value: Any) -> str:
    text = str(value or "").strip()
    return text.replace(",", "") if is_money_search_query(text) else text
