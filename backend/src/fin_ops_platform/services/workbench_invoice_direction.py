from __future__ import annotations

from typing import Any, Literal


InvoiceKind = Literal["input", "output"]
FlowDirection = Literal["inflow", "outflow"]
WorkbenchDirection = Literal["income", "expenditure"]

_INPUT_ALIASES = {
    "input",
    "input_invoice",
    "in_invoice",
    "purchase",
    "purchase_invoice",
    "payable",
}
_OUTPUT_ALIASES = {
    "output",
    "output_invoice",
    "out_invoice",
    "sales",
    "sale",
    "sales_invoice",
    "receivable",
}
_OA_ATTACHMENT_INVOICE_SOURCE_KIND = "oa_attachment_invoice"


def normalize_invoice_kind(value: Any) -> InvoiceKind | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.lower().replace("-", "_").replace(" ", "_")
    if normalized in _OUTPUT_ALIASES or "销项" in text:
        return "output"
    if normalized in _INPUT_ALIASES or "进项" in text:
        return "input"
    return None


def normalize_invoice_kind_from_row(row: dict[str, Any]) -> InvoiceKind | None:
    kind = normalize_invoice_kind(row.get("invoice_type"))
    if kind is not None:
        return kind
    if str(row.get("source_kind") or "").strip() == _OA_ATTACHMENT_INVOICE_SOURCE_KIND:
        return "input"
    return None


def invoice_flow_direction(value: Any) -> FlowDirection | None:
    kind = normalize_invoice_kind(value)
    if kind == "output":
        return "inflow"
    if kind == "input":
        return "outflow"
    return None


def invoice_flow_direction_from_row(row: dict[str, Any]) -> FlowDirection | None:
    kind = normalize_invoice_kind_from_row(row)
    if kind == "output":
        return "inflow"
    if kind == "input":
        return "outflow"
    return None


def invoice_workbench_direction(value: Any) -> WorkbenchDirection | None:
    kind = normalize_invoice_kind(value)
    if kind == "output":
        return "income"
    if kind == "input":
        return "expenditure"
    return None


def invoice_workbench_direction_from_row(row: dict[str, Any]) -> WorkbenchDirection | None:
    kind = normalize_invoice_kind_from_row(row)
    if kind == "output":
        return "income"
    if kind == "input":
        return "expenditure"
    return None


def invoice_counterparty_field(value: Any) -> str | None:
    kind = normalize_invoice_kind(value)
    if kind == "output":
        return "buyer_name"
    if kind == "input":
        return "seller_name"
    return None


def invoice_counterparty_field_from_row(row: dict[str, Any]) -> str | None:
    kind = normalize_invoice_kind_from_row(row)
    if kind == "output":
        return "buyer_name"
    if kind == "input":
        return "seller_name"
    return None
