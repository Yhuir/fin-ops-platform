from __future__ import annotations

from typing import Any


class CostStatisticsReadModelRepositoryPort:
    """Narrow read-side port for the cost_statistics read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def get_cost_statistics_scope_metadata(self, *, scope_key: str) -> dict[str, Any] | None:
        payload = self._repository.get_cost_statistics_scope_metadata(scope_key=scope_key)
        return dict(payload) if isinstance(payload, dict) else None

    def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, Any] | None:
        payload = self._repository.get_cost_statistics_freshness_gate(scope_key=scope_key)
        return dict(payload) if isinstance(payload, dict) else None

    def get_cost_statistics_page(self, **query: Any) -> dict[str, Any] | None:
        payload = self._repository.get_cost_statistics_page(**query)
        return dict(payload) if isinstance(payload, dict) else None

    def get_cost_statistics_export_page(self, **query: Any) -> dict[str, Any] | None:
        payload = self._repository.get_cost_statistics_export_page(**query)
        return dict(payload) if isinstance(payload, dict) else None

    def get_cost_statistics_transaction(
        self,
        *,
        project_scope: str,
        transaction_id: str,
    ) -> dict[str, Any] | None:
        payload = self._repository.get_cost_statistics_transaction(
            project_scope=project_scope,
            transaction_id=transaction_id,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def active_workbench_source_versions(self, *, scope_key: str) -> dict[str, Any]:
        payload = self._repository.active_workbench_source_versions(scope_key=scope_key)
        return dict(payload) if isinstance(payload, dict) else {}

    def acknowledge_unchanged_cost_statistics_scope(
        self,
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        source_versions: dict[str, Any],
    ) -> bool:
        return bool(
            self._repository.acknowledge_unchanged_cost_statistics_scope(
                tenant_id=tenant_id,
                scope_key=scope_key,
                source_version=source_version,
                source_versions=source_versions,
            )
        )

    def publish_cost_statistics_read_models(
        self,
        snapshot: dict[str, Any],
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        changed_scope_keys: set[str] | None = None,
    ) -> bool:
        return bool(
            self._repository.publish_cost_statistics_read_models(
                snapshot,
                tenant_id=tenant_id,
                scope_key=scope_key,
                source_version=source_version,
                changed_scope_keys=changed_scope_keys,
            )
        )

    def publish_cost_statistics_relation_delta(
        self,
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        model: dict[str, Any],
        replacement_rows: list[dict[str, Any]],
        affected_transaction_ids: list[str],
        affected_group_ids: list[str],
    ) -> bool:
        return bool(
            self._repository.publish_cost_statistics_relation_delta(
                tenant_id=tenant_id,
                scope_key=scope_key,
                source_version=source_version,
                model=model,
                replacement_rows=replacement_rows,
                affected_transaction_ids=affected_transaction_ids,
                affected_group_ids=affected_group_ids,
            )
        )
