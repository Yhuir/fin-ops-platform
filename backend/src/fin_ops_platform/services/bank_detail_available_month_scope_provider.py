from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import re
from typing import Any, Callable


SEARCH_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class BankDetailAvailableMonthScopeProvider:
    def __init__(
        self,
        *,
        import_service: Any,
        read_model_repository: Any | None = None,
        serialize_value: Callable[[Any], Any] | None = None,
        fallback_to_import_service: bool = True,
    ) -> None:
        self._import_service = import_service
        self._read_model_repository = read_model_repository
        self._serialize_value = serialize_value or self._default_serialize_value
        self._fallback_to_import_service = bool(fallback_to_import_service)

    def scope_keys(self) -> list[str]:
        repository_scope_keys = self._scope_keys_from_read_model_repository()
        if repository_scope_keys is not None:
            return repository_scope_keys or ["all"]
        if not self._fallback_to_import_service:
            return ["all"]
        return self._scope_keys_from_import_service()

    def _scope_keys_from_read_model_repository(self) -> list[str] | None:
        loader = getattr(self._read_model_repository, "bank_detail_scope_keys_for_range", None)
        if not callable(loader):
            return None
        return self._normalize_scope_keys(loader(date_from=None, date_to=None))

    def _scope_keys_from_import_service(self) -> list[str]:
        months: set[str] = set()
        try:
            transactions = self._import_service.list_transactions(month="all")
        except TypeError:
            transactions = self._import_service.list_transactions()
        except Exception:
            transactions = []
        for transaction in list(transactions or []):
            payload = self._serialize_value(transaction)
            if not isinstance(payload, dict):
                continue
            for key in ("txn_date", "trade_time", "pay_receive_time", "business_date", "transaction_at"):
                value = str(payload.get(key) or "").strip()
                if len(value) >= 7 and SEARCH_MONTH_RE.match(value[:7]):
                    months.add(value[:7])
                    break
        return sorted(months) or ["all"]

    @staticmethod
    def _normalize_scope_keys(values: Any) -> list[str]:
        months: set[str] = set()
        for value in list(values or []):
            scope_key = str(value or "").strip()
            if SEARCH_MONTH_RE.match(scope_key):
                months.add(scope_key)
        return sorted(months)

    @staticmethod
    def _default_serialize_value(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Enum):
            return value.value
        return value
