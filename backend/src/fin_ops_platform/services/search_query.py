from __future__ import annotations

import re
from typing import Any


_MONEY_QUERY_RE = re.compile(r"^[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$")


def normalize_money_search_query(value: Any) -> str:
    text = str(value or "").strip()
    return text.replace(",", "") if _MONEY_QUERY_RE.fullmatch(text) else text
