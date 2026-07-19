from __future__ import annotations

from typing import Any


class WorkbenchRelationReadModelRepositoryPort:
    """Narrow read-side port for the workbench_relation read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def get_workbench_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object] | None:
        payload = self._repository.get_workbench_relation_rows_by_ids(
            row_ids,
            tenant_id=tenant_id,
            scope_keys_hint=scope_keys_hint,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def get_batch_accounting_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
        submitted_year: str | None = None,
    ) -> dict[str, object] | None:
        payload = self._repository.get_batch_accounting_relation_rows_by_ids(
            row_ids,
            tenant_id=tenant_id,
            scope_keys_hint=scope_keys_hint,
            submitted_year=submitted_year,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def list_workbench_relation_rows(
        self,
        *,
        month: str,
        row_types: list[str] | None = None,
        relation_status: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        payload = self._repository.list_workbench_relation_rows(
            month=month,
            row_types=row_types,
            relation_status=relation_status,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def get_workbench_relation_groups_by_ids(
        self,
        group_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, object] | None:
        payload = self._repository.get_workbench_relation_groups_by_ids(
            group_ids,
            tenant_id=tenant_id,
            scope_keys_hint=scope_keys_hint,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def workbench_relation_source_versions(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
    ) -> dict[str, object]:
        payload = self._repository.workbench_relation_source_versions(
            scope_key=scope_key,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def list_active_workbench_relation_source_rows(
        self,
        *,
        row_ids: list[str],
        include_member_summaries: bool = False,
        tenant_id: str = "default",
    ) -> list[dict[str, object]]:
        rows = self._repository.list_active_workbench_relation_source_rows(
            row_ids=row_ids,
            include_member_summaries=include_member_summaries,
            tenant_id=tenant_id,
        )
        return [dict(row) for row in list(rows or []) if isinstance(row, dict)]

    def workbench_relation_source_summary_from_source(
        self,
        *,
        scope_key: str,
        row_ids: list[str] | None = None,
        include_row_ids: bool = False,
        tenant_id: str = "default",
    ) -> dict[str, object]:
        payload = self._repository.workbench_relation_source_summary_from_source(
            scope_key=scope_key,
            row_ids=row_ids,
            include_row_ids=include_row_ids,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def workbench_relation_scope_summary(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        payload = self._repository.workbench_relation_scope_summary(
            scope_key=scope_key,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def list_batch_accounting_relation_groups_by_year(
        self,
        *,
        year: str,
        tenant_id: str = "default",
    ) -> dict[str, object] | None:
        payload = self._repository.list_batch_accounting_relation_groups_by_year(
            year=year,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def save_workbench_relation_distribution(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        groups: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._repository.save_workbench_relation_distribution(
            scope_key=scope_key,
            rows=rows,
            groups=groups,
            source_versions=source_versions,
            tenant_id=tenant_id,
        )

    def save_workbench_relation_distribution_rows(
        self,
        *,
        scope_key: str,
        affected_row_ids: list[str],
        rows: list[dict[str, object]],
        groups: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._repository.save_workbench_relation_distribution_rows(
            scope_key=scope_key,
            affected_row_ids=affected_row_ids,
            rows=rows,
            groups=groups,
            source_versions=source_versions,
            tenant_id=tenant_id,
        )

    def mark_workbench_relation_scope_empty(
        self,
        *,
        scope_key: str,
        source_versions: dict[str, object] | None = None,
        tenant_id: str = "default",
    ) -> None:
        self._repository.mark_workbench_relation_scope_empty(
            scope_key=scope_key,
            source_versions=source_versions,
            tenant_id=tenant_id,
        )
