"""Workbench search text stays lossless; amount formatting never rewrites IDs."""

import re
from decimal import Decimal

_AMOUNT_FRAGMENT = re.compile(r"^[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d*)?|\.\d*)$")


def search_terms(value: str) -> list[str]:
    return list(dict.fromkeys(value.strip().split()))


def amount_search_fragment(value: str) -> str | None:
    fragment = value.removeprefix("￥").removeprefix("¥")
    if not _AMOUNT_FRAGMENT.fullmatch(fragment):
        return None
    return fragment.replace(",", "").removeprefix("+")


def fold_amount_search_minimum(fragment: str) -> Decimal | None:
    """Smallest nonnegative two-decimal display containing a validated fragment.

    This only prunes fold candidates; it never rewrites the search identity.
    None means that a positive bank fold cannot contain this fragment.
    """
    if fragment.startswith("-"):
        return None
    integer, dot, fraction = fragment.partition(".")
    if dot:
        if len(fraction) > 2:
            return None
        if len(integer) > 1 and integer.startswith("0"):
            integer = "1" + integer
        return Decimal((integer or "0") + "." + (fraction or "0"))
    if len(integer) <= 2:
        return Decimal(integer) / 100
    return Decimal("1" + integer if integer.startswith("0") else integer)
