from __future__ import annotations

from typing import Any, Iterable

EXPLICIT_EXPENSE_ITEM_SOURCE_TYPE = "oa_expense_item_invoice"


class InvoiceSourceLinksCasConflict(RuntimeError):
    def __init__(self, message: str, *, invoice_id: str | None = None) -> None:
        super().__init__(message)
        self.invoice_id = str(invoice_id or "").strip()


def source_links(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def has_oa_attachment_source(value: Any) -> bool:
    """OA provenance cannot be changed by import or inferred assignment.

    An unresolved historical item is still OA provenance: repair its identity,
    rather than guessing a different item or replacing it with a manual source.
    """
    return any(link.get("source_type") == "oa_attachment_invoice" for link in source_links(value))


def effective_invoice_source_links(value: Any) -> list[dict[str, Any]]:
    """Keep OA ownership and independent sources; import history lives in batches."""
    links = source_links(value)
    if not has_oa_attachment_source(links):
        return links
    return [link for link in links if link.get("source_type") not in {
        "manual_invoice_import", EXPLICIT_EXPENSE_ITEM_SOURCE_TYPE,
    }]


def effective_invoice_source_tags(tags: Iterable[str], links: Any) -> list[str]:
    oa_owned = has_oa_attachment_source(links)
    return [tag for tag in tags if not (
        oa_owned and tag in {"人工导入", "明细归属"}
    )]


def explicit_expense_item_links(value: Any) -> list[dict[str, Any]]:
    return [
        item
        for item in source_links(value)
        if _text(item.get("source_type")) == EXPLICIT_EXPENSE_ITEM_SOURCE_TYPE
    ]


def replace_explicit_expense_item_links(
    value: Any,
    *,
    case_id: str | None,
    targets: Iterable[tuple[str, str]],
    entry_method: str,
) -> list[dict[str, Any]]:
    """Replace explicit ownership edges while preserving all other provenance.

    ``case_id`` is intentionally optional for verified source-identity repairs:
    an ownership edge must not invent a Workbench presentation or formal relation id.
    """

    normalized_case_id = _text(case_id)
    if has_oa_attachment_source(value):
        raise ValueError("OA附件发票归属由原始子付款项确定，不能人工更改。")
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
    assigned = []
    for oa_row_id, expense_item_id in normalized_targets:
        link = {
            "source_type": EXPLICIT_EXPENSE_ITEM_SOURCE_TYPE,
            "source_workbench_row_id": oa_row_id,
            "derived_from_oa_id": oa_row_id,
            "source_expense_item_id": expense_item_id,
            "entry_method": normalized_entry_method,
        }
        if normalized_case_id:
            link["source_relation_case_id"] = normalized_case_id
        assigned.append(link)
    return [*preserved, *assigned]


def _required_text(value: Any, field_name: str) -> str:
    normalized = _text(value)
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _text(value: Any) -> str:
    return str(value or "").strip()
