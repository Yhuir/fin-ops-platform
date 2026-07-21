from __future__ import annotations

from typing import Any


class TaxOffsetReadModelRepositoryPort:
    """Narrow read-side port for the tax_offset read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def load_tax_offset_read_models(self) -> dict[str, Any]:
        payload = self._repository.load_tax_offset_read_models()
        return dict(payload) if isinstance(payload, dict) else {}

    def get_tax_offset_view(self, *, scope_key: str) -> dict[str, Any] | None:
        payload = self._repository.get_tax_offset_view(scope_key=scope_key)
        return dict(payload) if isinstance(payload, dict) else None

    def tax_offset_statistics_generation_token(self) -> str | None:
        loader = getattr(self._repository, "tax_offset_statistics_generation_token", None)
        value = loader() if callable(loader) else None
        return str(value) if value not in (None, "") else None

    def save_tax_offset_read_models(
        self,
        snapshot: dict[str, Any],
        *,
        changed_scope_keys: set[str] | None = None,
    ) -> None:
        self._repository.save_tax_offset_read_models(
            snapshot,
            changed_scope_keys=changed_scope_keys,
        )
