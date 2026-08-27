from __future__ import annotations

import re
from typing import Any, Iterable


REVERSED_BLUE_INVOICE_NO_SQL_PATTERN = (
    r"被红冲蓝字数电发票号码\s*[：:]\s*([0-9]{20})([^0-9]|$)"
)
_REVERSED_BLUE_INVOICE_NO_PATTERN = re.compile(
    r"被红冲蓝字数电发票号码\s*[：:]\s*(\d{20})(?!\d)"
)


def reversal_target_invoice_nos(remarks: Iterable[Any]) -> list[str]:
    """Extract only the exact red-invoice remark contract, preserving order."""

    invoice_nos: list[str] = []
    for remark in remarks:
        for invoice_no in _REVERSED_BLUE_INVOICE_NO_PATTERN.findall(
            str(remark or "")
        ):
            if invoice_no not in invoice_nos:
                invoice_nos.append(invoice_no)
    return invoice_nos


def unique_reversal_target_invoice_no(remark: Any) -> str | None:
    invoice_nos = reversal_target_invoice_nos([remark])
    return invoice_nos[0] if len(invoice_nos) == 1 else None
