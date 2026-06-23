from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Callable

from fin_ops_platform.services.bank_details_service import BankDetailsService
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService


class BankDetailAutoCategorySuggestionProvider:
    def __init__(
        self,
        *,
        import_service: Any,
        bank_details_service: BankDetailsService,
        bank_transaction_auto_category_service: BankTransactionAutoCategoryService,
        serialize_value: Callable[[Any], Any] | None = None,
    ) -> None:
        self._import_service = import_service
        self._bank_details_service = bank_details_service
        self._bank_transaction_auto_category_service = bank_transaction_auto_category_service
        self._serialize_value = serialize_value or self._default_serialize_value

    def latest(self, transaction_id: str) -> dict[str, object] | None:
        normalized_transaction_id = str(transaction_id or "").strip()
        transaction = self._import_service.get_transaction(normalized_transaction_id)
        row = self._serialize_value(transaction)
        if not isinstance(row, dict):
            row = dict(row or {})
        row["id"] = normalized_transaction_id
        input_row = self._bank_details_service.auto_category_input_row(row)
        return self._bank_transaction_auto_category_service.suggest_for_rows([input_row]).get(normalized_transaction_id)

    @staticmethod
    def _default_serialize_value(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Enum):
            return value.value
        return value
