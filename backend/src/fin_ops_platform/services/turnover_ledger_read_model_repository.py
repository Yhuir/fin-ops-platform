from __future__ import annotations

from typing import Any


class TurnoverLedgerReadModelRepositoryPort:
    """Narrow read-side port for the turnover_ledger read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def list_turnover_ledger_view(
        self,
        *,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
        scope_key: str = "all",
    ) -> dict[str, Any] | None:
        payload = self._repository.list_turnover_ledger_view(
            family=family,
            direction=direction,
            status=status,
            page=page,
            page_size=page_size,
            scope_key=scope_key,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def save_turnover_ledger_rows(self, payload: dict[str, Any], *, scope_key: str | None = None) -> None:
        self._repository.save_turnover_ledger_rows(payload, scope_key=scope_key)

    def load_turnover_ledger_relation_delta(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
    ) -> dict[str, Any]:
        payload = self._repository.load_turnover_ledger_relation_delta(
            scope_key=scope_key,
            row_ids=row_ids,
        )
        return dict(payload) if isinstance(payload, dict) else {}

    def save_turnover_ledger_relation_delta(
        self,
        payload: dict[str, Any],
        *,
        scope_key: str,
    ) -> None:
        self._repository.save_turnover_ledger_relation_delta(payload, scope_key=scope_key)
