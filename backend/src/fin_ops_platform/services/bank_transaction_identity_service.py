from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction

CENT = Decimal("0.01")
PLACEHOLDER_EMPTY_VALUES = {"", "--", "—", "-", "——", "nan", "NaN", "None"}
WHITESPACE_RE = re.compile(r"\s+")
DATE_TIME_RE = re.compile(r"^(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2}):(\d{2})$")
COMPACT_DATE_TIME_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})[ T]?(\d{2})(\d{2})(\d{2})$")


@dataclass(frozen=True, slots=True)
class BankTransactionIdentity:
    identity_key: str | None
    suspected_key: str | None = None
    canonical_key_kind: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    components: dict[str, str] = field(default_factory=dict)
    audit_fields: dict[str, str | None] = field(default_factory=dict)

    @property
    def is_stable(self) -> bool:
        return self.identity_key is not None


class BankTransactionIdentityService:
    def identity_for_mapping(self, values: dict[str, Any]) -> BankTransactionIdentity:
        account_no = clean_placeholder(values.get("account_no"))
        trade_time = self._normalize_trade_time(
            values.get("trade_time") or values.get("pay_receive_time") or values.get("txn_date")
        )
        direction = self._normalize_direction(values.get("txn_direction") or values.get("direction"))
        amount = self._normalize_amount(values, direction)
        counterparty_name = self._normalize_counterparty_name(values)

        components: dict[str, str] = {}
        missing_fields: list[str] = []
        for field_name, value in (
            ("account_no", account_no),
            ("trade_time", trade_time),
            ("direction", direction),
            ("amount", amount),
            ("counterparty_name", counterparty_name),
        ):
            if value:
                components[field_name] = value
            else:
                missing_fields.append(field_name)

        audit_fields = {
            "bank_serial_no": clean_placeholder(values.get("bank_serial_no")),
            "account_detail_no": clean_placeholder(values.get("account_detail_no")),
            "enterprise_serial_no": clean_placeholder(values.get("enterprise_serial_no")),
            "voucher_no": clean_placeholder(values.get("voucher_no")),
        }
        suspected_key = None if missing_fields else (
            f"bank:{components['account_no']}:{components['trade_time']}:{components['direction']}:"
            f"{components['amount']}:{components['counterparty_name']}"
        )
        reference_kind, reference = self._official_reference(audit_fields)
        if account_no and reference_kind and reference:
            identity_key = f"bank-v2:{account_no}:{reference_kind}:{reference}"
            if suspected_key:
                identity_key = f"bank-v3:{account_no}:{reference_kind}:{reference}:{sha256(suspected_key.encode()).hexdigest()[:16]}"
        else:
            identity_key = None
        return BankTransactionIdentity(
            identity_key=identity_key,
            suspected_key=suspected_key,
            canonical_key_kind=reference_kind,
            missing_fields=[] if identity_key or suspected_key else missing_fields,
            components=components,
            audit_fields=audit_fields,
        )

    def identity_for_transaction(self, transaction: BankTransaction) -> BankTransactionIdentity:
        values = {
            "account_no": transaction.account_no,
            "trade_time": transaction.trade_time,
            "pay_receive_time": transaction.pay_receive_time,
            "txn_date": transaction.txn_date,
            "txn_direction": transaction.txn_direction,
            "amount": transaction.amount,
            "counterparty_name": transaction.counterparty_name_raw,
            "bank_serial_no": transaction.bank_serial_no,
            "account_detail_no": transaction.account_detail_no,
            "enterprise_serial_no": transaction.enterprise_serial_no,
            "voucher_no": transaction.voucher_no,
        }
        return self.identity_for_mapping(values)

    def canonical_key_for_mapping(self, values: dict[str, Any]) -> str | None:
        return self.identity_for_mapping(values).identity_key

    def canonical_key_for_transaction(self, transaction: BankTransaction) -> str | None:
        return self.identity_for_transaction(transaction).identity_key

    @staticmethod
    def _official_reference(audit_fields: dict[str, str | None]) -> tuple[str | None, str | None]:
        for field_name in ("account_detail_no", "bank_serial_no", "enterprise_serial_no"):
            value = audit_fields.get(field_name)
            if value:
                normalized = WHITESPACE_RE.sub("", unicodedata.normalize("NFKC", value)).upper()
                if normalized:
                    return field_name, normalized
        return None, None

    @staticmethod
    def _normalize_trade_time(value: Any) -> str | None:
        if isinstance(value, datetime):
            return value.replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(value, date):
            return None
        text = clean_placeholder(value)
        if text is None:
            return None
        match = DATE_TIME_RE.match(text)
        if match:
            return (
                f"{match.group(1)}-{match.group(2)}-{match.group(3)} "
                f"{match.group(4)}:{match.group(5)}:{match.group(6)}"
            )
        match = COMPACT_DATE_TIME_RE.match(text)
        if match:
            return (
                f"{match.group(1)}-{match.group(2)}-{match.group(3)} "
                f"{match.group(4)}:{match.group(5)}:{match.group(6)}"
            )
        return None

    @staticmethod
    def _normalize_direction(value: Any) -> str | None:
        direction = clean_placeholder(getattr(value, "value", value))
        if direction is None:
            return None
        normalized = direction.strip().lower()
        if normalized in {TransactionDirection.INFLOW.value, "收入", "收款", "入账", "贷方", "credit", "in"}:
            return TransactionDirection.INFLOW.value
        if normalized in {TransactionDirection.OUTFLOW.value, "支出", "付款", "出账", "借方", "debit", "out"}:
            return TransactionDirection.OUTFLOW.value
        return None

    @staticmethod
    def _normalize_amount(values: dict[str, Any], direction: str | None) -> str | None:
        amount_value = values.get("amount")
        if clean_placeholder(amount_value) is None and direction == TransactionDirection.INFLOW.value:
            amount_value = values.get("credit_amount")
        if clean_placeholder(amount_value) is None and direction == TransactionDirection.OUTFLOW.value:
            amount_value = values.get("debit_amount")
        cleaned = clean_placeholder(amount_value)
        if cleaned is None:
            return None
        try:
            return f"{Decimal(str(cleaned).replace(',', '')).quantize(CENT)}"
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _normalize_counterparty_name(values: dict[str, Any]) -> str | None:
        normalized = clean_placeholder(values.get("normalized_counterparty_name"))
        if normalized:
            return normalize_name(normalized)
        raw_name = clean_placeholder(values.get("counterparty_name") or values.get("counterparty_name_raw"))
        if raw_name is None:
            return None
        normalized_name = normalize_name(raw_name)
        return normalized_name or None


def clean_placeholder(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in PLACEHOLDER_EMPTY_VALUES:
        return None
    return text or None


def normalize_name(value: str) -> str:
    return WHITESPACE_RE.sub(" ", str(value).strip()).lower()
