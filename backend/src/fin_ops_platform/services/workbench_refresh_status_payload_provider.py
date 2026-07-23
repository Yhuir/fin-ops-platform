from __future__ import annotations

from typing import Callable

from fin_ops_platform.services.workbench_refresh_status_payload import WorkbenchRefreshStatusPayloadNormalizer


class WorkbenchRefreshStatusPayloadProvider:
    """Read-only provider for normalized Workbench refresh-status payloads."""

    def __init__(
        self,
        *,
        repository_provider: Callable[[], object | None],
        source_freshness: Callable[..., dict[str, object]],
        normalizer: WorkbenchRefreshStatusPayloadNormalizer,
    ) -> None:
        self._repository_provider = repository_provider
        self._source_freshness = source_freshness
        self._normalizer = normalizer

    def payload_for_scope(self, scope_key: str) -> dict[str, object]:
        repository = self._repository_provider()
        get_refresh_status = getattr(repository, "get_workbench_groups_freshness_status", None)
        if not callable(get_refresh_status):
            get_refresh_status = getattr(repository, "get_workbench_refresh_status", None)
        if not callable(get_refresh_status):
            return self._normalizer.normalize(
                {},
                scope_key=scope_key,
                fallback_status="unavailable",
            )
        payload = get_refresh_status(scope_key=scope_key)
        if isinstance(payload, dict):
            payload = self._source_freshness(payload, scope_key=scope_key)
        return self._normalizer.normalize(
            payload if isinstance(payload, dict) else {},
            scope_key=scope_key,
            fallback_status="unavailable" if not isinstance(payload, dict) else "fresh",
        )
