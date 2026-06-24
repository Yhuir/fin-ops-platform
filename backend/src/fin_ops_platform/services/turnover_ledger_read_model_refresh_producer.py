from __future__ import annotations

from typing import Any, Callable


class TurnoverLedgerReadModelRefreshProducer:
    def __init__(
        self,
        *,
        refresh_gateway_provider: Callable[[], Any],
        read_repository_provider: Callable[[], Any | None],
    ) -> None:
        self._refresh_gateway_provider = refresh_gateway_provider
        self._read_repository_provider = read_repository_provider

    def enqueue(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        refresh_gateway = self._refresh_gateway_provider()
        if not refresh_gateway.can_enqueue():
            return False
        target_scope_keys = self._normalize_scope_keys(scope_keys)
        return bool(refresh_gateway.enqueue_many("turnover_ledger", target_scope_keys, reason=reason, metadata=metadata))

    def clear_best_effort(self) -> None:
        repository = self._read_repository_provider()
        clear_rows = getattr(repository, "clear_turnover_ledger_rows", None)
        if not callable(clear_rows):
            return
        try:
            clear_rows()
        except Exception:
            pass

    @staticmethod
    def _normalize_scope_keys(scope_keys: list[str]) -> list[str]:
        normalized_scope_keys: list[str] = []
        for item in list(scope_keys or []):
            scope_key = str(item).strip()
            if not scope_key:
                continue
            if scope_key == "all" or _is_month_scope(scope_key):
                normalized_scope_keys.append(scope_key)
        if not normalized_scope_keys:
            normalized_scope_keys = ["all"]
        return sorted(dict.fromkeys(normalized_scope_keys))


def _is_month_scope(scope_key: str) -> bool:
    parts = scope_key.split("-")
    if len(parts) != 2:
        return False
    year, month = parts
    if len(year) != 4 or len(month) != 2:
        return False
    return year.isdigit() and month.isdigit()
