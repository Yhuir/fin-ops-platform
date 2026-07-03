from __future__ import annotations

from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_linking import (
    oa_attachment_best_source_link,
    oa_attachment_matches_oa,
)


class WorkbenchOaAttachmentSourceLinkResolver:
    """Resolves OA attachment invoice source links to source OA row ids."""

    @staticmethod
    def source_link_for_invoice(invoice: object, oa_row_ids: set[str]) -> dict[str, str] | None:
        source_links: list[dict[str, object]] = []
        for link in list(getattr(invoice, "source_links", []) or []):
            if not isinstance(link, dict):
                continue
            if str(link.get("source_type") or "").strip() != "oa_attachment_invoice":
                continue
            normalized_link = {str(key): str(value) for key, value in link.items() if value is not None}
            if not normalized_link.get("derived_from_oa_id") and getattr(invoice, "oa_form_id", None):
                normalized_link["derived_from_oa_id"] = str(getattr(invoice, "oa_form_id") or "")
            source_links.append(normalized_link)
        best_link = oa_attachment_best_source_link(source_links, "oa_attachment_invoice", oa_row_ids=oa_row_ids)
        return {str(key): str(value) for key, value in best_link.items()} if best_link is not None else None

    @staticmethod
    def source_oa_id_for_attachment_link(source_link: dict[str, str], oa_row_ids: set[str]) -> str | None:
        link_row: dict[str, Any] = {
            "id": source_link.get("source_workbench_row_id"),
            "source_workbench_row_id": source_link.get("source_workbench_row_id"),
            "derived_from_oa_id": source_link.get("derived_from_oa_id"),
            "source_expense_item_id": source_link.get("source_expense_item_id"),
        }
        for oa_row_id in sorted(oa_row_ids):
            if oa_attachment_matches_oa(link_row, oa_row_id):
                return oa_row_id
        return None
