from __future__ import annotations

from typing import Any, Callable


class BankAccountBalanceReadModelRefreshProducer:
    def __init__(self, *, refresh_gateway_provider: Callable[[], Any]) -> None:
        self._refresh_gateway_provider = refresh_gateway_provider

    def enqueue(
        self,
        scope_keys: list[str] | None = None,
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return bool(self.enqueue_scope_keys(scope_keys or ["all"], reason=reason, metadata=metadata))

    def enqueue_all(
        self,
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return self.enqueue(["all"], reason=reason, metadata=metadata)

    def enqueue_scope_keys(
        self,
        scope_keys: list[str] | None = None,
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        refresh_gateway = self._refresh_gateway_provider()
        if not refresh_gateway.can_enqueue():
            return []
        return list(
            refresh_gateway.enqueue_many(
                "bank_account_balance",
                self.normalize_scope_keys(scope_keys),
                reason=reason,
                metadata=metadata,
            )
            or []
        )

    @staticmethod
    def normalize_scope_keys(_scope_keys: list[str] | None = None) -> list[str]:
        return ["all"]
