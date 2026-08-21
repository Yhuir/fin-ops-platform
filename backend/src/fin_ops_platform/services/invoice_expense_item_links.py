from __future__ import annotations

from typing import Any, Iterable


EXPLICIT_EXPENSE_ITEM_SOURCE_TYPE = "oa_expense_item_invoice"


class InvoiceSourceLinksCasConflict(RuntimeError):
    def __init__(self, message: str, *, invoice_id: str | None = None) -> None:
        super().__init__(message)
        self.invoice_id = str(invoice_id or "").strip()


def source_links(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def explicit_expense_item_links(value: Any) -> list[dict[str, Any]]:
    return [
        item
        for item in source_links(value)
        if _text(item.get("source_type")) == EXPLICIT_EXPENSE_ITEM_SOURCE_TYPE
    ]


def replace_explicit_expense_item_links(
    value: Any,
    *,
    case_id: str,
    targets: Iterable[tuple[str, str]],
    entry_method: str,
) -> list[dict[str, Any]]:
    """Replace only explicit item ownership edges and preserve all other provenance."""

    normalized_case_id = _required_text(case_id, "case_id")
    normalized_entry_method = _required_text(entry_method, "entry_method")
    normalized_targets = sorted(
        {
            (
                _required_text(oa_row_id, "oa_row_id"),
                _required_text(expense_item_id, "expense_item_id"),
            )
            for oa_row_id, expense_item_id in targets
        }
    )
    if not normalized_targets:
        raise ValueError("At least one OA expense-item target is required.")
    preserved = [
        item
        for item in source_links(value)
        if _text(item.get("source_type")) != EXPLICIT_EXPENSE_ITEM_SOURCE_TYPE
    ]
    assigned = [
        {
            "source_type": EXPLICIT_EXPENSE_ITEM_SOURCE_TYPE,
            "source_workbench_row_id": oa_row_id,
            "derived_from_oa_id": oa_row_id,
            "source_expense_item_id": expense_item_id,
            "source_relation_case_id": normalized_case_id,
            "entry_method": normalized_entry_method,
        }
        for oa_row_id, expense_item_id in normalized_targets
    ]
    return [*preserved, *assigned]


def _required_text(value: Any, field_name: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _text(value: Any) -> str:
    return str(value or "").strip()
