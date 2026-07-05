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
        rows = self._load_account_balance_rows()
        generated_at = datetime.now(UTC).isoformat()
        source_versions = {
            "source_version": source_version,
            "bank_account_balance_schema_version": BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
            "row_count": len(rows),
        }
        balance_rows = []
        for row in rows:
            balance_rows.append(
                {
                    "account_identity": text(row.get("account_identity")) or "",
                    "account_key": text(row.get("account_key") or row.get("account_identity")) or "",
                    "bank_name": text(row.get("bank_name")) or "未知银行",
                    "account_last4": text(row.get("account_last4")) or "unknown",
                    "account_no": text(row.get("account_no")),
                    "account_name": text(row.get("account_name")),
                    "identity_confidence": text(row.get("identity_confidence")) or "fallback",
                    "currency": _normalize_currency(row.get("currency")),
                    "transaction_total_count": int(row.get("transaction_total_count") or 0),
                    "latest_balance": decimal_text(row.get("latest_balance")),
                    "latest_balance_at": _time_text(row.get("latest_balance_at")),
                    "latest_balance_transaction_id": text(row.get("latest_balance_transaction_id")),
                    "latest_trade_time_sort": _time_text(row.get("latest_trade_time_sort")),
                    "latest_bank_serial_no": text(row.get("latest_bank_serial_no")),
                    "source_batch_id": text(row.get("source_batch_id")),
                    "legacy_source_batch_id": text(row.get("legacy_source_batch_id")),
                    "schema_version": BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
                    "source_versions": source_versions,
                    "generated_at": generated_at,
                    "raw_payload": row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {},
                }
            )
        self._read_model_repository.save_bank_account_balances(rows=balance_rows)
        return {"scope_key": "all", "row_count": len(balance_rows), "generated_at": generated_at}

    def _load_account_balance_rows(self) -> list[dict[str, Any]]:
        return list(
            self._connection.fetch_all(
                """
                with source_rows as (
                  select
                    coalesce(legacy_mongo_id, id::text) as row_id,
                    id::text as transaction_id,
                    source_batch_id::text as source_batch_id,
                    legacy_source_batch_id,
                    account_name,
                    balance,
                    currency,
                    txn_date,
                    trade_time,
                    coalesce(trade_time, txn_date::timestamptz) as trade_time_sort,
                    bank_serial_no,
                    case
                      when jsonb_typeof(raw_payload->'normalized_payload') = 'object'
                        then raw_payload->'normalized_payload'
                      else raw_payload
                    end as normalized_payload,
                    nullif(
                      regexp_replace(
                        coalesce(account_no, raw_payload->'normalized_payload'->>'account_no', raw_payload->>'account_no', ''),
                        '[^[:alnum:]]',
                        '',
                        'g'
                      ),
                      ''
                    ) as normalized_account_no
                  from app.bank_transactions
                  where (
                      balance is not null
                      or account_no is not null
                      or raw_payload is not null
                    )
                    and coalesce(nullif(status, ''), 'active') not in (
                      'deleted', 'void', 'voided', 'cancelled', 'canceled', 'ignored'
                    )
                ),
                account_fields as (
                  select
                    *,
                    coalesce(
                      nullif(normalized_payload->>'imported_bank_name', ''),
                      nullif(normalized_payload->>'bank_name', ''),
                      '未知银行'
                    ) as bank_name,
                    right(
                      coalesce(
                        nullif(normalized_payload->>'imported_bank_last4', ''),
                        nullif(normalized_payload->>'account_last4', ''),
                        normalized_account_no,
                        'unknown'
                      ),
                      4
                    ) as account_last4,
                    case
                      when currency is null or btrim(currency::text) = '' then 'CNY'
                      when upper(btrim(currency::text)) in ('CNY', 'RMB') then 'CNY'
                      when btrim(currency::text) in ('人民币', '人民币元', '元') then 'CNY'
                      else upper(btrim(currency::text))
                    end as normalized_currency
                  from source_rows
                ),
                identity_rows as (
                  select
                    *,
                    case
                      when normalized_account_no is not null and normalized_account_no <> ''
                        then 'acct:' || substring(encode(digest(normalized_account_no, 'sha256'), 'hex') from 1 for 24)
                      else 'fallback:' || substring(
                        encode(digest(lower(btrim(bank_name)) || ':' || coalesce(nullif(account_last4, ''), 'unknown'), 'sha256'), 'hex')
                        from 1 for 24
                      )
                    end as account_identity,
                    case
                      when normalized_account_no is not null and normalized_account_no <> '' then 'account_no'
                      else 'bank_last4'
                    end as identity_confidence
                  from account_fields
                ),
                account_base as (
                  select distinct on (account_identity)
                    account_identity,
                    account_identity as account_key,
                    bank_name,
                    account_last4,
                    normalized_account_no as account_no,
                    account_name,
                    identity_confidence,
                    normalized_currency as currency
                  from identity_rows
                  order by account_identity, trade_time_sort desc nulls last, bank_serial_no desc nulls last, row_id desc
                ),
                account_counts as (
                  select account_identity, count(*)::bigint as transaction_total_count
                  from identity_rows
                  group by account_identity
                ),
                latest_balances as (
                  select distinct on (account_identity)
                    account_identity,
                    balance as latest_balance,
                    coalesce(trade_time::text, txn_date::text) as latest_balance_at,
                    row_id as latest_balance_transaction_id,
                    trade_time_sort as latest_trade_time_sort,
                    bank_serial_no as latest_bank_serial_no,
                    source_batch_id,
                    legacy_source_batch_id,
                    jsonb_build_object(
                      'latest_transaction',
                      jsonb_build_object(
                        'id', row_id,
                        'transaction_id', transaction_id,
                        'balance', balance,
                        'trade_time', trade_time,
                        'trade_date', txn_date,
                        'trade_time_sort', trade_time_sort,
                        'bank_serial_no', bank_serial_no,
                        'source_batch_id', source_batch_id,
                        'legacy_source_batch_id', legacy_source_batch_id
                      )
                    ) as raw_payload
                  from identity_rows
                  where balance is not null
                  order by account_identity, trade_time_sort desc nulls last, bank_serial_no desc nulls last, row_id desc
                )
                select
                  account_base.account_identity,
                  account_base.account_key,
                  account_base.bank_name,
                  account_base.account_last4,
                  account_base.account_no,
                  account_base.account_name,
                  account_base.identity_confidence,
                  account_base.currency,
                  account_counts.transaction_total_count,
                  latest_balances.latest_balance,
                  latest_balances.latest_balance_at,
                  latest_balances.latest_balance_transaction_id,
                  latest_balances.latest_trade_time_sort,
                  latest_balances.latest_bank_serial_no,
                  latest_balances.source_batch_id,
                  latest_balances.legacy_source_batch_id,
                  coalesce(latest_balances.raw_payload, '{}'::jsonb) as raw_payload
                from account_base
                join account_counts on account_counts.account_identity = account_base.account_identity
                left join latest_balances on latest_balances.account_identity = account_base.account_identity
                order by account_base.bank_name, account_base.account_last4, account_base.account_identity
                """,
                (),
            )
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
