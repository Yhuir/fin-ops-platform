from __future__ import annotations

from typing import Any


class InvoiceLifecycleReadModelRepositoryPort:
    """Narrow read-side port for the invoice_lifecycle read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def save_invoice_lifecycle_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self._repository.save_invoice_lifecycle_rows(
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
        )

    def mark_invoice_lifecycle_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self._repository.mark_invoice_lifecycle_scope(
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
        )

    def get_invoice_lifecycle_rows_by_subject_ids(
        self,
        subject_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        payload = self._repository.get_invoice_lifecycle_rows_by_subject_ids(
            subject_ids,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def get_invoice_lifecycle_rows_by_identity_keys(
        self,
        invoice_identity_keys: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        payload = self._repository.get_invoice_lifecycle_rows_by_identity_keys(
            invoice_identity_keys,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def list_invoice_lifecycle_rows(
        self,
        *,
        month: str,
        subject_types: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        payload = self._repository.list_invoice_lifecycle_rows(
            month=month,
            subject_types=subject_types,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def invoice_lifecycle_scope_summary(
        self,
        *,
        month: str,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        payload = self._repository.invoice_lifecycle_scope_summary(
            month=month,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else None
