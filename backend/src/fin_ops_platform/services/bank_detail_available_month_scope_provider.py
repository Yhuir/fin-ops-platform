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
        serialize_value: Callable[[Any], Any] | None = None,
    ) -> None:
        self._import_service = import_service
        self._serialize_value = serialize_value or self._default_serialize_value

    def scope_keys(self) -> list[str]:
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
    def _default_serialize_value(value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Enum):
            return value.value
        return value
