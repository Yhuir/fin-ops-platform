from __future__ import annotations

from typing import Any


class CostStatisticsReadModelRepositoryPort:
    """Narrow read-side port for the cost_statistics read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def load_cost_statistics_read_models(self) -> dict[str, Any]:
        payload = self._repository.load_cost_statistics_read_models()
        return dict(payload) if isinstance(payload, dict) else {}

    def get_cost_statistics_view(self, *, scope_key: str) -> dict[str, Any] | None:
        payload = self._repository.get_cost_statistics_view(scope_key=scope_key)
        return dict(payload) if isinstance(payload, dict) else None

    def save_cost_statistics_read_models(
        self,
        snapshot: dict[str, Any],
        *,
        changed_scope_keys: set[str] | None = None,
    ) -> None:
        self._repository.save_cost_statistics_read_models(
            snapshot,
            changed_scope_keys=changed_scope_keys,
        )
