from __future__ import annotations

from typing import Any


class BankAccountBalanceReadModelRepositoryPort:
    """Narrow read-side port for the bank_account_balance read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def bank_account_balance_scope_summary(self, *, tenant_id: str = "default", connection: Any | None = None) -> dict[str, Any]:
        payload = self._repository.bank_account_balance_scope_summary(tenant_id=tenant_id, connection=connection)
        return dict(payload) if isinstance(payload, dict) else {}

    def list_bank_account_balances(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        payload = self._repository.list_bank_account_balances(
            date_from=date_from,
            date_to=date_to,
            tenant_id=tenant_id,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def save_bank_account_balances(self, *, rows: list[dict[str, Any]], tenant_id: str = "default") -> None:
        self._repository.save_bank_account_balances(rows=rows, tenant_id=tenant_id)
