"""发票四要素的有界补算；保留原值，推算比例不是来源税率。"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.output_invoice_tax_rate import normalize_output_tax_rate

MONEY_FIELDS = ("amount", "tax_amount", "total_with_tax")
PUBLIC_FIELDS = {"amount": "amount", "tax_amount": "taxAmount", "total_with_tax": "totalWithTax", "tax_rate": "taxRate"}
CENT = Decimal("0.01")


@dataclass(frozen=True)
class InvoiceFinancialValues:
    amount: Decimal | None
    tax_amount: Decimal | None
    total_with_tax: Decimal | None
    tax_rate: str | None
    inferred_fields: tuple[str, ...]
    issue: str | None = None

    @property
    def rate_label(self) -> str:
        label = normalize_output_tax_rate(self.tax_rate)
        return label + ("（推算）" if "tax_rate" in self.inferred_fields else "")


def resolve_invoice_financial_values(
    *, amount: Any, tax_amount: Any, total_with_tax: Any, tax_rate: Any,
    inferred_fields: tuple[str, ...] | list[str] = (), specific_business_type: Any = None,
) -> InvoiceFinancialValues:
    """只用同一粒度的原始金额。缺一项金额时做加减；税率仅用三个原始金额推算。"""
    values: dict[str, Decimal | None] = {}
    for key, raw in zip(MONEY_FIELDS, (amount, tax_amount, total_with_tax), strict=True):
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            values[key] = None
            continue
        try:
            number = Decimal(str(raw))
        except InvalidOperation as exc:
            raise ValueError(f"Invalid invoice {key}") from exc
        if not number.is_finite():
            raise ValueError(f"Invalid invoice {key}")
        values[key] = number
    rate = str(tax_rate).strip() if tax_rate is not None else ""
    inferred = set(inferred_fields)
    missing = [key for key, value in values.items() if value is None]
    if len(missing) == 1:
        key = missing[0]
        a, t, g = (values[field] for field in MONEY_FIELDS)
        values[key] = {"amount": lambda: g - t, "tax_amount": lambda: g - a,
                       "total_with_tax": lambda: a + t}[key]().quantize(CENT, rounding=ROUND_HALF_UP)
        inferred.add(key)
    a, t, g = (values[field] for field in MONEY_FIELDS)
    issue = None
    if all(value is not None for value in (a, t, g)):
        if (a + t).quantize(CENT, rounding=ROUND_HALF_UP) != g.quantize(CENT, rounding=ROUND_HALF_UP):
            issue = "金额、税额与价税合计不一致"
        elif a * t < 0 or a * g < 0:
            issue = "发票金额与税额符号不一致"
        elif (missing and not str(specific_business_type or "").strip()
              and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", normalize_output_tax_rate(rate))
              and abs(a * Decimal(normalize_output_tax_rate(rate)[:-1]) / 100 - t) > CENT):
            issue = "来源税率与金额不一致"
        elif (not rate and not inferred.intersection(MONEY_FIELDS) and a != 0 and t != 0
              and not str(specific_business_type or "").strip()):
            # 优先两位小数百分比，必须能按分复算原税额；否则保留六位。
            percentage = (t / a * 100).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            compact = (t / a * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if (a * compact / 100).quantize(CENT, rounding=ROUND_HALF_UP) == t.quantize(CENT, rounding=ROUND_HALF_UP):
                percentage = compact
            rate = format(percentage, "f").rstrip("0").rstrip(".") + "%"
            inferred.add("tax_rate")
    if issue and missing:
        values[missing[0]] = None
        inferred.discard(missing[0])
    return InvoiceFinancialValues(**values, tax_rate=rate or None,
                                  inferred_fields=tuple(sorted(inferred)), issue=issue)


def invoice_financial_values(invoice: Any) -> InvoiceFinancialValues:
    return resolve_invoice_financial_values(
        amount=invoice.amount, tax_amount=invoice.tax_amount, total_with_tax=invoice.total_with_tax,
        tax_rate=invoice.tax_rate, inferred_fields=invoice.inferred_fields,
        specific_business_type=invoice.specific_business_type,
    )


def invoice_financial_summary(lines: list[Any]) -> dict[str, Any]:
    values = [invoice_financial_values(line) for line in lines]
    result: dict[str, Any] = {}
    for field in MONEY_FIELDS:
        parts = [getattr(value, field) for value in values]
        result[PUBLIC_FIELDS[field]] = (format(sum(parts, Decimal("0")), ".2f")
                                       if all(part is not None for part in parts) else "")
    labels = {normalize_output_tax_rate(value.tax_rate) for value in values}
    result["taxRate"] = next(iter(labels)) if len(labels) == 1 else "多税率"
    if len(labels) == 1 and any("tax_rate" in value.inferred_fields for value in values):
        result["taxRate"] += "（推算）"
    result["inferredFields"] = sorted({PUBLIC_FIELDS[field] for value in values for field in value.inferred_fields})
    result["amountWithoutTax"] = result["amount"]
    return result
