from __future__ import annotations

from typing import Any


class BankDetailReadModelRepositoryPort:
    """Narrow read-side port for the bank_detail read model."""

    def __init__(self, repository: Any) -> None:
        self._repository = repository

    def bank_detail_scope_keys_for_range(self, *, date_from: str | None, date_to: str | None) -> list[str]:
        return list(
            self._repository.bank_detail_scope_keys_for_range(
                date_from=date_from,
                date_to=date_to,
            )
            or []
        )

    def bank_detail_scope_summary(self, *, scope_keys: list[str]) -> dict[str, object]:
        payload = self._repository.bank_detail_scope_summary(scope_keys=scope_keys)
        return dict(payload) if isinstance(payload, dict) else {}

    def list_bank_detail_transactions(
        self,
        *,
        account_key: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        category_code: str | None = None,
        category_primary_label: str | None = None,
        category_sub_label: str | None = None,
        category_third_label: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, object] | None:
        payload = self._repository.list_bank_detail_transactions(
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
            page=page,
            page_size=page_size,
        )
        return dict(payload) if isinstance(payload, dict) else None

    def list_bank_detail_accounts(self, *, date_from: str | None = None, date_to: str | None = None) -> dict[str, object] | None:
        payload = self._repository.list_bank_detail_accounts(date_from=date_from, date_to=date_to)
        return dict(payload) if isinstance(payload, dict) else None
