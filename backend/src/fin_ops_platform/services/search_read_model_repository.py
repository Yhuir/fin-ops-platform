from __future__ import annotations

from typing import Any


class SearchReadModelRepositoryPort:
    """Narrow read-side port for the search read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository
        self._connection = getattr(repository, "_connection", None)

    def search_index(
        self,
        *,
        q: str,
        scope: str,
        month: str,
        project_name: str | None,
        status: str | None,
        limit: int,
    ) -> dict[str, Any] | None:
        payload = self._repository.search_index(
            q=q,
            scope=scope,
            month=month,
            project_name=project_name,
            status=status,
            limit=limit,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def save_search_index_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        self._repository.save_search_index_rows(
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
        )
