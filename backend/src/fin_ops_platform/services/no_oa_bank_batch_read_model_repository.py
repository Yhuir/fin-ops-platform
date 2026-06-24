from __future__ import annotations

from typing import Any


class NoOaBankBatchReadModelRepositoryPort:
    """Narrow read-side port for the no_oa_bank_batch read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def list_no_oa_bank_batch_rows(self, filters: dict[str, object] | None = None) -> list[dict[str, Any]] | None:
        rows = self._repository.list_no_oa_bank_batch_rows(filters)
        return list(rows) if rows is not None else None
