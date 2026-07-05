from __future__ import annotations

from typing import Any, Callable


class TurnoverLedgerReadModelRefreshProducer:
    def __init__(
        self,
        *,
        refresh_gateway_provider: Callable[[], Any],
    ) -> None:
        self._refresh_gateway_provider = refresh_gateway_provider

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
