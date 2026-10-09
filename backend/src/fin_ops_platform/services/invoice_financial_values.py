"""读取发票原始财务字段；缺失金额和税率不通过计算补齐。"""
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
    tax_amount_text: str | None = None
    issue: str | None = None

    @property
    def rate_label(self) -> str:
        return normalize_output_tax_rate(self.tax_rate)


def resolve_invoice_financial_values(
    *, amount: Any, tax_amount: Any, total_with_tax: Any, tax_rate: Any,
    tax_amount_text: str | None = None,
    source_line_items: list[dict[str, Any]] | None = None,
) -> InvoiceFinancialValues:
    """保留来源值；原始明细税率的归并不依赖金额或逐行价税合计。"""
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
    a, t, g = (values[field] for field in MONEY_FIELDS)
    issue = None
    if all(value is not None for value in (a, t, g)):
        if (a + t).quantize(CENT, rounding=ROUND_HALF_UP) != g.quantize(CENT, rounding=ROUND_HALF_UP):
            issue = "金额、税额与价税合计不一致"
        elif a * t < 0 or a * g < 0:
            issue = "发票金额与税额符号不一致"
    rate, rate_issue = _source_tax_rate(tax_rate, source_line_items or [])
    return InvoiceFinancialValues(
        **values, tax_rate=rate, tax_amount_text=(tax_amount_text.strip() or None) if tax_amount_text else None,
        issue=issue or rate_issue,
    )


def _source_tax_rate(
    raw_rate: Any, source_lines: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    header = normalize_output_tax_rate(raw_rate)
    source_lines = [line for line in source_lines if line.get("source_sheet_role") != "invoice_header"]
    if not source_lines:
        return (None if header == UNKNOWN_TAX_RATE else header), None
    labels = {normalize_output_tax_rate(line.get("tax_rate")) for line in source_lines}
    known = labels - {UNKNOWN_TAX_RATE}
    if header not in {UNKNOWN_TAX_RATE, MULTIPLE_TAX_RATES}:
        if known - {header}:
            return None, "来源税率与明细税率不一致"
        return header, None
    # Missing header rates remain missing; detail-rate summaries belong to the view.
    return (MULTIPLE_TAX_RATES if header == MULTIPLE_TAX_RATES else None), None



def invoice_financial_values(invoice: Any) -> InvoiceFinancialValues:
    return resolve_invoice_financial_values(
        amount=invoice.amount, tax_amount=invoice.tax_amount, total_with_tax=invoice.total_with_tax,
        tax_rate=invoice.tax_rate, tax_amount_text=invoice.tax_amount_text,
        source_line_items=invoice.source_line_items,
    )


def invoice_financial_summary(lines: list[Any]) -> dict[str, Any]:
    values = [invoice_financial_values(line) for line in lines]
    result: dict[str, Any] = {}
    for field in MONEY_FIELDS:
        parts = [getattr(value, field) for value in values]
        result[PUBLIC_FIELDS[field]] = (format(sum(parts, Decimal("0")), ".2f")
                                       if parts and all(part is not None for part in parts) else "")
    result["taxRate"] = combine_invoice_tax_rates(value.tax_rate for value in values)
    result["taxAmountText"] = values[0].tax_amount_text if len(values) == 1 else None
    result["amountWithoutTax"] = result["amount"]
    return result
