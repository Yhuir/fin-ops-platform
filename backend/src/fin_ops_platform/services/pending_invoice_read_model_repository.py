from __future__ import annotations

from typing import Any


class PendingInvoiceReadModelRepositoryPort:
    """Narrow read-side port for the pending_invoice read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def list_pending_invoice_rows(
        self,
        *,
        direction: str,
        filter: str,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str = 1,
        page_size: int | str = 50,
    ) -> dict[str, object] | None:
        payload = self._repository.list_pending_invoice_rows(
            direction=direction,
            filter=filter,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def list_pending_invoice_filter_options(
        self,
        *,
        direction: str,
        filter: str,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | None = None,
    ) -> dict[str, object]:
        payload = self._repository.list_pending_invoice_filter_options(
            direction=direction,
            filter=filter,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            filters=filters,
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def pending_invoice_source_summary(
        self,
        *,
        direction: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, int]:
        payload = self._repository.pending_invoice_source_summary(
            direction=direction,
            date_from=date_from,
            date_to=date_to,
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def pending_invoice_bank_detail_source_versions(
        self,
        *,
        direction: str,
        filter: str,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | None = None,
    ) -> dict[str, object]:
        payload = self._repository.pending_invoice_bank_detail_source_versions(
            direction=direction,
            filter=filter,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            filters=filters,
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def pending_invoice_workbench_relation_source_versions(
        self,
        *,
        direction: str,
        filter: str,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | None = None,
    ) -> dict[str, object]:
        payload = self._repository.pending_invoice_workbench_relation_source_versions(
            direction=direction,
            filter=filter,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            filters=filters,
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def save_pending_invoice_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self._repository.save_pending_invoice_rows(
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
        )

    def mark_pending_invoice_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self._repository.mark_pending_invoice_scope(
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
        )
