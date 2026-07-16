from __future__ import annotations

from contextlib import contextmanager
from typing import Any


class OaPendingPaymentReadModelRepositoryPort:
    """Narrow read-side port for the oa_pending_payment read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def list_oa_pending_payment_rows(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        trade_date_from: str | None = None,
        trade_date_to: str | None = None,
        filters: str | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str = 1,
        page_size: int | str = 50,
        view_mode: str | None = None,
    ) -> dict[str, object] | None:
        payload = self._repository.list_oa_pending_payment_rows(
            month=month,
            keyword=keyword,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            filters=filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
            view_mode=view_mode,
        )
        return dict(payload) if isinstance(payload, dict) else None

    @contextmanager
    def read_snapshot(self):
        snapshot = getattr(self._repository, "oa_pending_payment_read_snapshot", None)
        if not callable(snapshot):
            yield self
            return
        with snapshot() as repository:
            yield OaPendingPaymentReadModelRepositoryPort(repository)

    def query_state(
        self,
        *,
        scope_key: str,
        tenant_id: str,
        base_source_versions: dict[str, object],
    ) -> dict[str, object] | None:
        loader = getattr(self._repository, "oa_pending_payment_query_state", None)
        if not callable(loader):
            return None
        payload = loader(
            scope_key=scope_key,
            tenant_id=tenant_id,
            base_source_versions=base_source_versions,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def get_oa_pending_payment_row_by_row_id(self, row_id: str) -> dict[str, object] | None:
        payload = self._repository.get_oa_pending_payment_row_by_row_id(row_id)
        return dict(payload) if isinstance(payload, dict) else None

    def get_oa_pending_payment_row_by_oa_id(self, oa_id: str) -> dict[str, object] | None:
        payload = self._repository.get_oa_pending_payment_row_by_oa_id(oa_id)
        return dict(payload) if isinstance(payload, dict) else None

    def get_oa_pending_payment_row_by_bank_transaction_id(self, bank_transaction_id: str) -> dict[str, object] | None:
        payload = self._repository.get_oa_pending_payment_row_by_bank_transaction_id(bank_transaction_id)
        return dict(payload) if isinstance(payload, dict) else None

    def get_oa_pending_payment_row_by_invoice_id(self, invoice_id: str) -> dict[str, object] | None:
        payload = self._repository.get_oa_pending_payment_row_by_invoice_id(invoice_id)
        return dict(payload) if isinstance(payload, dict) else None

    def save_oa_pending_payment_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self._repository.save_oa_pending_payment_rows(
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
        )

    def publish_oa_pending_payment_rows(
        self,
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> bool:
        publish = getattr(self._repository, "publish_oa_pending_payment_rows", None)
        if not callable(publish):
            raise RuntimeError("OA pending payment repository does not support atomic CAS publish.")
        published_source_versions = {
            **dict(source_versions or {}),
            "oa_pending_payment_event_source_version": source_version,
        }
        return bool(
            publish(
                tenant_id=tenant_id,
                scope_key=scope_key,
                source_version=source_version,
                rows=rows,
                source_versions=published_source_versions,
            )
        )

    def mark_oa_pending_payment_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self._repository.mark_oa_pending_payment_scope(
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
        )

    def prune_oa_pending_payment_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._repository.prune_oa_pending_payment_scope_shards(current_scope_keys)
