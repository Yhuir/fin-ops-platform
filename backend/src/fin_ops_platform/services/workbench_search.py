"""Workbench search text stays lossless; amount formatting never rewrites IDs."""

import re

_AMOUNT_FRAGMENT = re.compile(r"^[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d*)?|\.\d*)$")


def search_terms(value: str) -> list[str]:
    return list(dict.fromkeys(value.strip().split()))


def amount_search_fragment(value: str) -> str | None:
    fragment = value.removeprefix("￥").removeprefix("¥")
    if not _AMOUNT_FRAGMENT.fullmatch(fragment):
        return None
    return fragment.replace(",", "").removeprefix("+")
