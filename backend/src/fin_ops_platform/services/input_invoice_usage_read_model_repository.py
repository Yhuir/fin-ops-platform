from __future__ import annotations

from typing import Any


class InputInvoiceUsageReadModelRepositoryPort:
    """Narrow read-side port for the input_invoice_usage read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def list_input_invoice_usage_rows(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
    ) -> dict[str, object] | None:
        payload = self._repository.list_input_invoice_usage_rows(
            month=month,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def list_input_invoice_usage_filter_options(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
    ) -> dict[str, object] | None:
        payload = self._repository.list_input_invoice_usage_filter_options(
            month=month,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            filters=filters,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def get_input_invoice_usage_row_by_row_id(self, row_id: str) -> dict[str, object] | None:
        payload = self._repository.get_input_invoice_usage_row_by_row_id(row_id)
        return dict(payload) if isinstance(payload, dict) else None

    def save_input_invoice_usage_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self._repository.save_input_invoice_usage_rows(
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
        )

    def mark_input_invoice_usage_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self._repository.mark_input_invoice_usage_scope(
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
        )

    def prune_input_invoice_usage_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._repository.prune_input_invoice_usage_scope_shards(current_scope_keys)
