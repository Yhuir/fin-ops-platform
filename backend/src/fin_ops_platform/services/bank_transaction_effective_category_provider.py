from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BankTransactionAutoCategoryService,
    resolve_effective_category,
)
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService


class BankTransactionEffectiveCategoryProvider:
    def __init__(
        self,
        *,
        category_service: BankTransactionCategoryService,
        auto_category_service: BankTransactionAutoCategoryService,
    ) -> None:
        self._category_service = category_service
        self._auto_category_service = auto_category_service

    def get(self, transaction_id: str) -> dict[str, Any]:
        manual = self._category_service.get(transaction_id)
        return self._category_record(
            transaction_id=str(transaction_id or "").strip(),
            effective=resolve_effective_category(manual, None),
            manual=manual,
        )

    def bulk_get(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        manual_by_id = self._category_service.bulk_get(transaction_ids)
        return {
            transaction_id: self._category_record(
                transaction_id=transaction_id,
                effective=resolve_effective_category(manual, None),
                manual=manual,
            )
            for transaction_id, manual in manual_by_id.items()
        }

    def bulk_get_for_rows(self, bank_rows: list[Any]) -> dict[str, dict[str, Any]]:
        rows = [self._bank_row_payload(row) for row in list(bank_rows or [])]
        rows_by_id = {
            str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip(): row
            for row in rows
            if str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()
        }
        transaction_ids = list(rows_by_id.keys())
        manual_by_id = self._category_service.bulk_get(transaction_ids)
        auto_by_id = self._auto_category_service.suggestions_by_transaction_id(list(rows_by_id.values()))
        return {
            transaction_id: self._category_record(
                transaction_id=transaction_id,
                effective=resolve_effective_category(
                    manual_by_id.get(transaction_id),
                    auto_by_id.get(transaction_id),
                ),
                manual=manual_by_id.get(transaction_id),
            )
            for transaction_id in transaction_ids
        }

    @classmethod
    def _bank_row_payload(cls, row: Any) -> dict[str, Any]:
        if is_dataclass(row):
            payload = asdict(row)
        elif isinstance(row, dict):
            payload = dict(row)
        else:
            payload = {
                key: getattr(row, key)
                for key in dir(row)
                if not key.startswith("_") and not callable(getattr(row, key, None))
            }

        transaction_id = str(payload.get("id") or payload.get("transaction_id") or payload.get("row_id") or "").strip()
        if transaction_id:
            payload["id"] = transaction_id

        if not str(payload.get("counterparty_name") or "").strip():
            payload["counterparty_name"] = str(payload.get("counterparty_name_raw") or "").strip()

        direction = cls._direction(payload)
        amount = payload.get("amount")
        if payload.get("debit_amount") in (None, "") and direction == "outflow":
            payload["debit_amount"] = cls._amount_text(amount)
        if payload.get("credit_amount") in (None, "") and direction == "inflow":
            payload["credit_amount"] = cls._amount_text(amount)
        payload.setdefault("type", "bank")
        return payload

    @staticmethod
    def _direction(row: dict[str, Any]) -> str:
        value = row.get("txn_direction") or row.get("direction")
        if isinstance(value, TransactionDirection):
            value = value.value
        elif hasattr(value, "value"):
            value = value.value
        normalized = str(value or "").strip().lower()
        if normalized in {"inflow", "income", "收", "进"}:
            return "inflow"
        if normalized in {"outflow", "expense", "支", "出"}:
            return "outflow"
        signed = row.get("signed_amount")
        if signed not in (None, ""):
            try:
                return "inflow" if Decimal(str(signed)) > Decimal("0") else "outflow"
            except (InvalidOperation, ValueError):
                return ""
        return ""

    @staticmethod
    def _amount_text(value: Any) -> str:
        if value in (None, "", "--", "—"):
            return ""
        try:
            return f"{Decimal(str(value)).copy_abs():.2f}"
        except (InvalidOperation, ValueError):
            return str(value)

    @staticmethod
    def _category_record(
        *,
        transaction_id: str,
        effective: dict[str, Any],
        manual: dict[str, Any] | None,
    ) -> dict[str, Any]:
        category_code = effective.get("effective_category_code")
        category_source = str(effective.get("effective_category_source") or "").strip()
        category_version = 0
        if isinstance(manual, dict) and str(manual.get("source") or "").strip() in {"manual", "auto_confirmation"}:
            category_version = int(manual.get("category_version") or 0)
        return {
            "transaction_id": transaction_id,
            "category_code": category_code,
            "category_label": effective.get("effective_category_label"),
            "category_path": list(effective.get("effective_category_path") or []),
            "category_source": category_source,
            "source": category_source,
            "category_version": category_version,
            **effective,
        }
