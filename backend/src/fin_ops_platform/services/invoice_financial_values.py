"""发票金额加减补齐与来源税率判定；不把金额比例当作税率。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.output_invoice_tax_rate import (
    MULTIPLE_TAX_RATES,
    UNKNOWN_TAX_RATE,
    combine_invoice_tax_rates,
    normalize_output_tax_rate,
)

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
        return normalize_output_tax_rate(self.tax_rate)


def resolve_invoice_financial_values(
    *, amount: Any, tax_amount: Any, total_with_tax: Any, tax_rate: Any,
    inferred_fields: tuple[str, ...] | list[str] = (),
    source_line_items: list[dict[str, Any]] | None = None,
) -> InvoiceFinancialValues:
    """同粒度金额缺一项时做加减；税率只读取来源字段或有覆盖证据的来源明细。"""
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
    inferred = set(inferred_fields) - {"tax_rate"}
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
    if issue and missing:
        values[missing[0]] = None
        inferred.discard(missing[0])
    rate, rate_issue = _source_tax_rate(tax_rate, inferred_fields, source_line_items or [], values)
    return InvoiceFinancialValues(**values, tax_rate=rate,
                                  inferred_fields=tuple(sorted(inferred)), issue=issue or rate_issue)


def _source_tax_rate(
    raw_rate: Any, inferred_fields: tuple[str, ...] | list[str],
    source_lines: list[dict[str, Any]], totals: dict[str, Decimal | None],
) -> tuple[str | None, str | None]:
    header = normalize_output_tax_rate(None if "tax_rate" in inferred_fields else raw_rate)
    if not source_lines:
        return (None if header == UNKNOWN_TAX_RATE else header), None
    lines = [resolve_invoice_financial_values(
        **{field: str(line[field]).replace(",", "") if line.get(field) is not None else None for field in MONEY_FIELDS},
        tax_rate=line.get("tax_rate"),
        inferred_fields=line.get("inferred_fields") or (),
    ) for line in source_lines]
    labels = {line.rate_label for line in lines}
    known = labels - {UNKNOWN_TAX_RATE}
    if header not in {UNKNOWN_TAX_RATE, MULTIPLE_TAX_RATES}:
        if known - {header}:
            return None, "来源税率与明细税率不一致"
        return header, None
    if MULTIPLE_TAX_RATES in known or len(known) > 1:
        return MULTIPLE_TAX_RATES, None
    if UNKNOWN_TAX_RATE in labels or not known or any(line.issue for line in lines):
        return None, None
    # 原始明细必须覆盖已知整票金额，不能把局部的一种税率当作整票税率。
    available = [(field, amount) for field, amount in totals.items() if amount is not None]
    if not available:
        return None, None
    for field, amount in available:
        parts = [getattr(line, field) for line in lines]
        if any(part is None for part in parts):
            return None, None
        if sum(parts, Decimal("0")).quantize(CENT, rounding=ROUND_HALF_UP) != amount.quantize(CENT, rounding=ROUND_HALF_UP):
            return None, None
    return next(iter(known)), None


def invoice_financial_values(invoice: Any) -> InvoiceFinancialValues:
    return resolve_invoice_financial_values(
        amount=invoice.amount, tax_amount=invoice.tax_amount, total_with_tax=invoice.total_with_tax,
        tax_rate=invoice.tax_rate, inferred_fields=invoice.inferred_fields,
        source_line_items=invoice.source_line_items,
    )


def invoice_financial_summary(lines: list[Any]) -> dict[str, Any]:
    values = [invoice_financial_values(line) for line in lines]
    result: dict[str, Any] = {}
    for field in MONEY_FIELDS:
        parts = [getattr(value, field) for value in values]
        result[PUBLIC_FIELDS[field]] = (format(sum(parts, Decimal("0")), ".2f")
                                       if all(part is not None for part in parts) else "")
    result["taxRate"] = combine_invoice_tax_rates(value.tax_rate for value in values)
    result["inferredFields"] = sorted({PUBLIC_FIELDS[field] for value in values for field in value.inferred_fields})
    result["amountWithoutTax"] = result["amount"]
    return result
