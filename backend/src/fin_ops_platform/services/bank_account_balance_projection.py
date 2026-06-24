from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from fin_ops_platform.services.bank_account_balance_read_model_repository import BankAccountBalanceReadModelRepositoryPort
from fin_ops_platform.services.postgres_repositories.common import decimal_text, text
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
    PostgresReadModelRepository,
)


INVALID_BANK_TRANSACTION_STATUSES = ("deleted", "void", "voided", "cancelled", "canceled", "ignored")


class BankAccountBalanceProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: Any | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = BankAccountBalanceReadModelRepositoryPort(
            read_model_repository or PostgresReadModelRepository(connection)
        )

    def rebuild_bank_account_balance_read_model(self, *, source_version: int | None = None) -> dict[str, Any]:
        rows = [self._normalize_transaction_row(row) for row in self._load_transaction_rows()]
        accounts: dict[str, dict[str, Any]] = {}
        latest_candidates: dict[str, dict[str, Any]] = {}
        for row in rows:
            account_identity = str(row.get("account_identity") or "").strip()
            if not account_identity:
                continue
            account = accounts.setdefault(
                account_identity,
                {
                    "account_identity": account_identity,
                    "account_key": row.get("account_key") or account_identity,
                    "bank_name": row.get("bank_name") or "未知银行",
                    "account_last4": row.get("account_last4") or "unknown",
                    "account_no": row.get("account_no"),
                    "account_name": row.get("account_name"),
                    "identity_confidence": row.get("identity_confidence") or "fallback",
                    "currency": row.get("currency") or "CNY",
                    "transaction_total_count": 0,
                },
            )
            account["transaction_total_count"] = int(account.get("transaction_total_count") or 0) + 1
            if row.get("balance") in (None, ""):
                continue
            current = latest_candidates.get(account_identity)
            if current is None or self._balance_sort_key(row) > self._balance_sort_key(current):
                latest_candidates[account_identity] = row

        generated_at = datetime.now(UTC).isoformat()
        source_versions = {
            "source_version": source_version,
            "bank_account_balance_schema_version": BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
            "row_count": len(accounts),
        }
        balance_rows = []
        for account_identity, account in sorted(accounts.items(), key=lambda item: (str(item[1].get("bank_name")), str(item[1].get("account_last4")), item[0])):
            latest = latest_candidates.get(account_identity)
            balance_rows.append(
                {
                    **account,
                    "latest_balance": latest.get("balance") if latest is not None else None,
                    "latest_balance_at": latest.get("trade_time") or latest.get("trade_date") if latest is not None else None,
                    "latest_balance_transaction_id": latest.get("id") if latest is not None else None,
                    "latest_trade_time_sort": latest.get("trade_time_sort") if latest is not None else None,
                    "latest_bank_serial_no": latest.get("bank_serial_no") if latest is not None else None,
                    "source_batch_id": latest.get("source_batch_id") if latest is not None else None,
                    "legacy_source_batch_id": latest.get("legacy_source_batch_id") if latest is not None else None,
                    "schema_version": BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
                    "source_versions": source_versions,
                    "generated_at": generated_at,
                    "raw_payload": {"latest_transaction": latest or {}, "account": account},
                }
            )
        self._read_model_repository.save_bank_account_balances(rows=balance_rows)
        return {"scope_key": "all", "row_count": len(balance_rows), "generated_at": generated_at}

    def _load_transaction_rows(self) -> list[dict[str, Any]]:
        return list(
            self._connection.fetch_all(
                """
                select coalesce(legacy_mongo_id, id::text) as id,
                       id::text as transaction_id,
                       source_batch_id::text,
                       legacy_source_batch_id,
                       account_no,
                       account_name,
                       balance,
                       currency,
                       txn_date,
                       trade_time,
                       coalesce(trade_time, txn_date::timestamptz) as trade_time_sort,
                       bank_serial_no,
                       raw_payload
                from app.bank_transactions
                where (
                    balance is not null
                    or account_no is not null
                    or raw_payload is not null
                  )
                  and (
                    status is null
                    or status not in ('deleted', 'void', 'voided', 'cancelled', 'canceled', 'ignored')
                  )
                order by coalesce(trade_time, txn_date::timestamptz) desc,
                         bank_serial_no desc nulls last,
                         coalesce(legacy_mongo_id, id::text) desc
                """,
                (),
            )
        )

    def _normalize_transaction_row(self, row: dict[str, Any]) -> dict[str, Any]:
        raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
        normalized_payload = raw_payload.get("normalized_payload") if isinstance(raw_payload.get("normalized_payload"), dict) else raw_payload
        bank_name = text(normalized_payload.get("imported_bank_name") or normalized_payload.get("bank_name")) or "未知银行"
        account_no = _normalize_account_no(row.get("account_no") or normalized_payload.get("account_no"))
        account_last4 = (
            text(normalized_payload.get("imported_bank_last4") or normalized_payload.get("account_last4"))
            or account_no
            or "unknown"
        )[-4:]
        account_identity, identity_confidence = _account_identity(
            account_no=account_no,
            bank_name=bank_name,
            account_last4=account_last4,
        )
        return {
            "id": text(row.get("id")) or "",
            "transaction_id": text(row.get("transaction_id")) or text(row.get("id")) or "",
            "source_batch_id": text(row.get("source_batch_id")),
            "legacy_source_batch_id": text(row.get("legacy_source_batch_id")),
            "account_identity": account_identity,
            "account_key": account_identity,
            "identity_confidence": identity_confidence,
            "bank_name": bank_name,
            "account_last4": account_last4 or "unknown",
            "account_no": account_no,
            "account_name": text(row.get("account_name")),
            "trade_time": _time_text(row.get("trade_time")),
            "trade_date": text(row.get("txn_date") or row.get("trade_time")),
            "trade_time_sort": _time_text(row.get("trade_time_sort") or row.get("trade_time") or row.get("txn_date")),
            "bank_serial_no": text(row.get("bank_serial_no")),
            "balance": decimal_text(row.get("balance")),
            "currency": _normalize_currency(row.get("currency")),
        }

    @staticmethod
    def _balance_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(row.get("trade_time_sort") or row.get("trade_time") or row.get("trade_date") or ""),
            str(row.get("bank_serial_no") or ""),
            str(row.get("id") or row.get("transaction_id") or ""),
        )


def _normalize_account_no(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip() if ch.isalnum())


def _account_identity(*, account_no: str, bank_name: str, account_last4: str) -> tuple[str, str]:
    if account_no:
        digest = sha256(account_no.encode("utf-8")).hexdigest()[:24]
        return f"acct:{digest}", "account_no"
    fallback = f"{bank_name.strip().lower()}:{account_last4 or 'unknown'}"
    digest = sha256(fallback.encode("utf-8")).hexdigest()[:24]
    return f"fallback:{digest}", "bank_last4"


def _time_text(value: Any) -> str:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(sep=" ")
    raw = str(value or "").strip().replace("T", " ")
    if len(raw) >= 25 and raw[19] in {"+", "-"} and raw[20:22].isdigit() and raw[23:25].isdigit():
        return raw[:19]
    if raw.endswith("Z") and len(raw) >= 20:
        return raw[:19]
    return raw


def _normalize_currency(value: Any) -> str:
    raw = text(value)
    if raw is None:
        return "CNY"
    normalized = raw.strip().upper()
    if normalized in {"CNY", "RMB"}:
        return "CNY"
    if raw.strip() in {"人民币", "人民币元", "元"}:
        return "CNY"
    return normalized or "CNY"
