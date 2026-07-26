from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Any, Iterator

from fin_ops_platform.services.bank_account_balance_projection import (
    BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL,
)
from fin_ops_platform.services.bank_details_service import BankDetailsService
from fin_ops_platform.services.bank_details_export_service import (
    BANK_DETAIL_EXPORT_ROW_LIMIT,
)
from fin_ops_platform.services.bank_settings import bank_accounts_from_settings_payload
from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BankTransactionAutoCategoryService,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryService,
    default_bank_transaction_tag_dictionary_payload,
)
from fin_ops_platform.services.import_file_service import COMPANY_NAME_KEYWORDS
from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    int_value,
    text,
    text_list,
)
from fin_ops_platform.services.workbench_relation_modes import (
    TURNOVER_MANUAL_CLOSURE_RELATION_MODE,
)
from fin_ops_platform.services.workbench_row_identity import (
    row_type_for_workbench_row_id,
)


INVALID_BANK_TRANSACTION_STATUSES = (
    "deleted",
    "void",
    "voided",
    "cancelled",
    "canceled",
    "ignored",
)
MAX_PAGE_SIZE = 500
MAX_EXPORT_ROWS = BANK_DETAIL_EXPORT_ROW_LIMIT
INTERNAL_TRANSFER_MARKERS = ("本公司帐户", "本公司账户", "本公司税户")


class PostgresBankDetailsCanonicalQueryRepository:
    """Page-specific SQL repository over canonical bank and relation facts."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Bank details canonical query repository requires PostgreSQL.")
        self._connection = connection

    def accounts_snapshot(
        self,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> dict[str, Any]:
        with self._snapshot_transaction() as transaction:
            settings = self._settings_payload(transaction)
            rows = transaction.fetch_all(BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL)
            counts = self._account_transaction_counts(
                transaction,
                date_from=date_from,
                date_to=date_to,
            )
        return {"settings": settings, "rows": rows, "transaction_counts": counts}

    def transactions_snapshot(
        self,
        *,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None,
        category_primary_label: str | None,
        category_sub_label: str | None,
        category_third_label: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 100), 1), MAX_PAGE_SIZE)
        with self._snapshot_transaction() as transaction:
            settings = self._settings_payload(transaction)
            snapshot = self._load_transaction_page(
                transaction,
                settings=settings,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                keyword=keyword,
                category_code=category_code,
                category_primary_label=category_primary_label,
                category_sub_label=category_sub_label,
                category_third_label=category_third_label,
                page=normalized_page,
                page_size=normalized_page_size,
            )
            relations = self._active_relations(
                transaction,
                row_ids=_transaction_relation_lookup_ids(snapshot["rows"]),
            )
        return {**snapshot, "settings": settings, "relations": relations}

    def export_snapshot(
        self,
        *,
        include_accounts: bool,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None,
        category_primary_label: str | None,
        category_sub_label: str | None,
        category_third_label: str | None,
    ) -> dict[str, Any]:
        with self._snapshot_transaction() as transaction:
            settings = self._settings_payload(transaction)
            snapshot = self._load_transaction_page(
                transaction,
                settings=settings,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                keyword=keyword,
                category_code=category_code,
                category_primary_label=category_primary_label,
                category_sub_label=category_sub_label,
                category_third_label=category_third_label,
                page=1,
                page_size=MAX_EXPORT_ROWS + 1,
            )
            relations = self._active_relations(
                transaction,
                row_ids=_transaction_relation_lookup_ids(snapshot["rows"]),
            )
            account_snapshot = None
            if include_accounts:
                account_snapshot = {
                    "settings": settings,
                    "rows": transaction.fetch_all(BANK_ACCOUNT_BALANCE_CANONICAL_ROWS_SQL),
                    "transaction_counts": self._account_transaction_counts(
                        transaction,
                        date_from=date_from,
                        date_to=date_to,
                    ),
                }
        return {
            **snapshot,
            "settings": settings,
            "relations": relations,
            "account_snapshot": account_snapshot,
        }

    @contextmanager
    def _snapshot_transaction(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction

    @staticmethod
    def _settings_payload(transaction: Any) -> dict[str, Any]:
        row = transaction.fetch_one(
            """
            select settings_payload
            from app.app_settings
            where settings_key = 'app_settings'
            limit 1
            """
        )
        payload = row.get("settings_payload") if isinstance(row, dict) else None
        return dict(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _account_transaction_counts(
        transaction: Any,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> dict[str, int]:
        rows = transaction.fetch_all(
            """
            with source_rows as (
              select
                txn_date,
                case
                  when jsonb_typeof(raw_payload->'normalized_payload') = 'object'
                    then raw_payload->'normalized_payload'
                  else raw_payload
                end as normalized_payload,
                nullif(
                  regexp_replace(
                    coalesce(
                      account_no,
                      raw_payload->'normalized_payload'->>'account_no',
                      raw_payload->>'account_no',
                      ''
                    ),
                    '[^[:alnum:]]',
                    '',
                    'g'
                  ),
                  ''
                ) as normalized_account_no
              from app.bank_transactions
              where coalesce(nullif(status, ''), 'active') <> all(%s::text[])
            ),
            account_rows as (
              select
                txn_date,
                case
                  when normalized_account_no is not null and normalized_account_no <> ''
                    then 'acct:' || substring(
                      encode(digest(normalized_account_no, 'sha256'), 'hex')
                      from 1 for 24
                    )
                  else 'fallback:' || substring(
                    encode(
                      digest(
                        lower(btrim(coalesce(
                          nullif(normalized_payload->>'imported_bank_name', ''),
                          nullif(normalized_payload->>'bank_name', ''),
                          '未知银行'
                        ))) || ':' || right(coalesce(
                          nullif(normalized_payload->>'imported_bank_last4', ''),
                          nullif(normalized_payload->>'account_last4', ''),
                          'unknown'
                        ), 4),
                        'sha256'
                      ),
                      'hex'
                    )
                    from 1 for 24
                  )
                end as account_identity
              from source_rows
            )
            select account_identity, count(*)::bigint as transaction_count
            from account_rows
            where (%s::date is null or txn_date >= %s::date)
              and (%s::date is null or txn_date <= %s::date)
            group by account_identity
            """,
            (
                list(INVALID_BANK_TRANSACTION_STATUSES),
                date_from,
                date_from,
                date_to,
                date_to,
            ),
        )
        return {
            text(row.get("account_identity")) or "": int_value(
                row.get("transaction_count"),
                0,
            )
            for row in rows
            if text(row.get("account_identity"))
        }

    def _load_transaction_page(
        self,
        transaction: Any,
        *,
        settings: dict[str, Any],
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None,
        category_primary_label: str | None,
        category_sub_label: str | None,
        category_third_label: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        tags = settings.get("bank_transaction_tags")
        if not isinstance(tags, dict):
            tags = default_bank_transaction_tag_dictionary_payload()
        definitions = [
            dict(item)
            for item in list(tags.get("definitions") or [])
            if isinstance(item, dict)
        ]
        cte_sql, cte_params = _classification_cte(
            definitions=definitions,
            date_from=date_from,
            date_to=date_to,
        )
        where_sql, where_params = _transaction_filter_sql(
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
        )
        rows = transaction.fetch_all(
            f"""
            with {cte_sql},
            filtered as materialized (
              select *
              from classified_with_semantics
              where {where_sql}
            ),
            category_counts as (
              select coalesce(
                jsonb_object_agg(category_code, category_count),
                '{{}}'::jsonb
              ) as counts
              from (
                select
                  coalesce(effective_category_code, 'uncategorized') as category_code,
                  count(*)::bigint as category_count
                from filtered
                group by coalesce(effective_category_code, 'uncategorized')
              ) grouped
            ),
            summary as (
              select
                count(*)::bigint as total,
                count(*) filter (where direction = 'expense')::bigint as expense_count,
                count(*) filter (where direction = 'income')::bigint as income_count,
                count(*) filter (where effective_category_code is not null)::bigint as classified_count,
                count(*) filter (where effective_category_code is null)::bigint as unclassified_count
              from filtered
            ),
            page_rows as (
              select *
              from filtered
              order by trade_time_sort desc nulls last, row_id desc
              limit %s offset %s
            )
            select
              page_rows.*,
              summary.total as result_total,
              summary.expense_count as result_expense_count,
              summary.income_count as result_income_count,
              summary.classified_count as result_classified_count,
              summary.unclassified_count as result_unclassified_count,
              category_counts.counts as result_category_counts
            from summary
            cross join category_counts
            left join page_rows on true
            order by page_rows.trade_time_sort desc nulls last, page_rows.row_id desc
            """,
            tuple(
                [
                    *cte_params,
                    *where_params,
                    page_size,
                    (page - 1) * page_size,
                ]
            ),
        )
        summary_row = rows[0] if rows else {}
        page_rows = [
            _without_summary_columns(row)
            for row in rows
            if text(row.get("row_id"))
        ]
        total = int_value(summary_row.get("result_total"), 0)
        return {
            "rows": page_rows,
            "category_counts": (
                dict(summary_row.get("result_category_counts"))
                if isinstance(summary_row.get("result_category_counts"), dict)
                else {}
            ),
            "statistics": {
                "transaction_count": total,
                "expense_transaction_count": int_value(
                    summary_row.get("result_expense_count"),
                    0,
                ),
                "income_transaction_count": int_value(
                    summary_row.get("result_income_count"),
                    0,
                ),
                "classified_transaction_count": int_value(
                    summary_row.get("result_classified_count"),
                    0,
                ),
                "unclassified_transaction_count": int_value(
                    summary_row.get("result_unclassified_count"),
                    0,
                ),
            },
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
            },
        }

    @staticmethod
    def _active_relations(
        transaction: Any,
        *,
        row_ids: list[str],
    ) -> list[dict[str, Any]]:
        if not row_ids:
            return []
        return list(
            transaction.fetch_all(
                """
                select case_id, row_ids, row_types
                from app.workbench_pair_relations
                where status = 'active'
                  and relation_mode <> %s
                  and row_ids && %s::text[]
                order by updated_at desc, case_id
                """,
                (TURNOVER_MANUAL_CLOSURE_RELATION_MODE, row_ids),
            )
        )


class BankDetailsCanonicalQueryService:
    def __init__(self, repository: PostgresBankDetailsCanonicalQueryRepository) -> None:
        self._repository = repository

    def accounts_payload(
        self,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> dict[str, Any]:
        _validate_date_range(date_from=date_from, date_to=date_to)
        return self._accounts_payload(
            self._repository.accounts_snapshot(
                date_from=date_from,
                date_to=date_to,
            )
        )

    def transactions_payload(
        self,
        *,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None,
        category_primary_label: str | None,
        category_sub_label: str | None,
        category_third_label: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        _validate_date_range(date_from=date_from, date_to=date_to)
        _validate_pagination(page=page, page_size=page_size)
        snapshot = self._repository.transactions_snapshot(
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
        return self._transactions_payload(
            snapshot,
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
        )

    def export_payload(
        self,
        *,
        include_accounts: bool,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None,
        category_primary_label: str | None,
        category_sub_label: str | None,
        category_third_label: str | None,
    ) -> dict[str, Any]:
        _validate_date_range(date_from=date_from, date_to=date_to)
        snapshot = self._repository.export_snapshot(
            include_accounts=include_accounts,
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
        )
        return {
            "transactions": self._transactions_payload(
                snapshot,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
            ),
            "accounts": (
                self._accounts_payload(snapshot["account_snapshot"])
                if isinstance(snapshot.get("account_snapshot"), dict)
                else None
            ),
        }

    @staticmethod
    def _accounts_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
        settings = (
            snapshot.get("settings")
            if isinstance(snapshot.get("settings"), dict)
            else {}
        )
        configured_by_last4 = {
            item["account_last4"]: item
            for item in bank_accounts_from_settings_payload(settings)
        }
        transaction_counts = (
            snapshot.get("transaction_counts")
            if isinstance(snapshot.get("transaction_counts"), dict)
            else {}
        )
        accounts: list[dict[str, Any]] = []
        totals_by_currency: dict[str, Decimal] = {}
        for row in list(snapshot.get("rows") or []):
            if not isinstance(row, dict):
                continue
            account_key = text(row.get("account_key") or row.get("account_identity")) or ""
            last4 = text(row.get("account_last4")) or "unknown"
            mapping = configured_by_last4.get(last4, {})
            bank_name = (
                text(mapping.get("bank_name"))
                or text(row.get("bank_name"))
                or "未知银行"
            )
            currency = text(row.get("currency")) or "CNY"
            latest_balance = row.get("latest_balance")
            has_balance = latest_balance is not None
            if has_balance:
                totals_by_currency[currency] = totals_by_currency.get(
                    currency,
                    Decimal("0.00"),
                ) + Decimal(str(latest_balance))
            accounts.append(
                {
                    "account_identity": text(row.get("account_identity")) or account_key,
                    "account_key": account_key,
                    "bank_name": bank_name,
                    "account_last4": last4,
                    "display_name": f"{bank_name} {last4}",
                    "account_no": text(row.get("account_no")),
                    "account_name": text(row.get("account_name")),
                    "identity_confidence": text(row.get("identity_confidence")) or "fallback",
                    "currency": currency,
                    "latest_balance": (
                        decimal_text(latest_balance)
                        if latest_balance is not None
                        else None
                    ),
                    "latest_balance_at": text(row.get("latest_balance_at")),
                    "latest_balance_transaction_id": text(
                        row.get("latest_balance_transaction_id")
                    ),
                    "has_balance": has_balance,
                    "transaction_count": int_value(
                        transaction_counts.get(account_key),
                        0,
                    ),
                    "transaction_total_count": int_value(
                        row.get("transaction_total_count"),
                        0,
                    ),
                }
            )
        total_balance = totals_by_currency.get("CNY")
        return {
            "accounts": accounts,
            "total_balance": (
                decimal_text(total_balance)
                if total_balance is not None
                else None
            ),
            "total_balances_by_currency": {
                currency: decimal_text(total)
                for currency, total in sorted(totals_by_currency.items())
            },
            "balance_account_count": sum(
                1 for account in accounts if account["has_balance"]
            ),
            "missing_balance_account_count": sum(
                1 for account in accounts if not account["has_balance"]
            ),
        }

    @staticmethod
    def _transactions_payload(
        snapshot: dict[str, Any],
        *,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
    ) -> dict[str, Any]:
        settings = (
            snapshot.get("settings")
            if isinstance(snapshot.get("settings"), dict)
            else {}
        )
        tags = settings.get("bank_transaction_tags")
        if not isinstance(tags, dict):
            tags = default_bank_transaction_tag_dictionary_payload()
        category_service = BankTransactionCategoryService()
        category_service.configure_tag_dictionary(tags)
        auto_service = BankTransactionAutoCategoryService(
            category_service=category_service
        )
        mapper = BankDetailsService(
            None,
            category_service=category_service,
            auto_category_service=auto_service,
        )
        relation_by_row_id = _relation_payloads_by_row_id(
            list(snapshot.get("relations") or []),
            list(snapshot.get("rows") or []),
        )
        rows: list[dict[str, Any]] = []
        for row in list(snapshot.get("rows") or []):
            if not isinstance(row, dict):
                continue
            row_id = text(row.get("row_id")) or ""
            auto_category = _auto_category_payload(
                row,
                category_service=category_service,
                auto_service=auto_service,
            )
            rows.append(
                mapper.row_payload(
                    {
                        **row,
                        "id": row_id,
                        "account_key": text(row.get("account_key")) or "",
                        "txn_direction": (
                            "inflow"
                            if text(row.get("direction")) == "income"
                            else "outflow"
                        ),
                    },
                    manual_category=_manual_category_payload(
                        row,
                        category_service=category_service,
                    ),
                    auto_category=auto_category,
                    relation=relation_by_row_id.get(row_id),
                )
            )
        category_counts = {
            str(code): int_value(count, 0)
            for code, count in dict(snapshot.get("category_counts") or {}).items()
        }
        for code in category_service.tag_count_keys():
            category_counts.setdefault(code, 0)
        category_counts.setdefault("uncategorized", 0)
        return {
            "account_key": account_key,
            "date_from": date_from,
            "date_to": date_to,
            "rows": rows,
            "category_counts": category_counts,
            "statistics": dict(snapshot.get("statistics") or {}),
            "bank_transaction_tags": tags,
            "pagination": dict(snapshot.get("pagination") or {}),
        }


def _classification_cte(
    *,
    definitions: list[dict[str, Any]],
    date_from: str | None,
    date_to: str | None,
) -> tuple[str, list[Any]]:
    tag_definitions_json = json.dumps(
        definitions,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    rule_sql, rule_params = _rule_match_union_sql(definitions)
    normalization_sql = _normalization_select_sql(definitions)
    params: list[Any] = [
        tag_definitions_json,
        "default",
        list(INVALID_BANK_TRANSACTION_STATUSES),
        date_from,
        date_from,
        date_to,
        date_to,
        [f"%{marker}%" for marker in INTERNAL_TRANSFER_MARKERS],
        [f"%{marker}%" for marker in INTERNAL_TRANSFER_MARKERS],
        [f"%{keyword}%" for keyword in COMPANY_NAME_KEYWORDS],
        [f"%{keyword}%" for keyword in COMPANY_NAME_KEYWORDS],
        *rule_params,
    ]
    return (
        f"""
        tag_definitions as materialized (
          select definition
          from jsonb_array_elements(%s::jsonb) as item(definition)
        ),
        source_rows as materialized (
          select
            coalesce(bank.legacy_mongo_id, bank.id::text) as row_id,
            bank.id::text as canonical_transaction_id,
            bank.source_batch_id::text as source_batch_id,
            bank.legacy_source_batch_id,
            bank.account_no,
            bank.account_name,
            bank.txn_direction,
            bank.counterparty_name_raw,
            bank.normalized_counterparty_name,
            bank.amount,
            bank.signed_amount,
            bank.balance,
            bank.currency,
            bank.txn_date,
            bank.trade_time,
            bank.pay_receive_time,
            coalesce(bank.trade_time, bank.txn_date::timestamptz) as trade_time_sort,
            bank.bank_serial_no,
            bank.summary,
            bank.remark,
            bank.bank_text_fields,
            bank.raw_payload,
            case
              when jsonb_typeof(bank.raw_payload->'normalized_payload') = 'object'
                then bank.raw_payload->'normalized_payload'
              else bank.raw_payload
            end as normalized_payload,
            manual.category as manual_category_code,
            manual.source as manual_category_source,
            manual.version as manual_category_version,
            manual.raw_payload as manual_category_raw_payload,
            confirmation.id as confirmation_id,
            confirmation.category_code as confirmed_category_code,
            confirmation.candidate_category_codes as confirmed_candidate_category_codes,
            confirmation.rule_version as confirmation_rule_version,
            confirmation.version as confirmation_version,
            confirmation.raw_payload as confirmation_raw_payload
          from app.bank_transactions bank
          left join lateral (
            select category, source, version, raw_payload
            from app.bank_transaction_categories category
            where category.status = 'active'
              and (
                category.bank_transaction_id = bank.id
                or category.legacy_transaction_id in (
                  coalesce(bank.legacy_mongo_id, bank.id::text),
                  bank.id::text
                )
              )
            order by category.updated_at desc, category.id desc
            limit 1
          ) manual on true
          left join lateral (
            select id, category_code, candidate_category_codes, rule_version,
                   version, raw_payload
            from app.bank_transaction_category_confirmations confirmation
            where confirmation.tenant_id = %s
              and confirmation.status = 'active'
              and (
                confirmation.bank_transaction_id = bank.id
                or confirmation.legacy_transaction_id in (
                  coalesce(bank.legacy_mongo_id, bank.id::text),
                  bank.id::text
                )
              )
            order by confirmation.confirmed_at desc, confirmation.id desc
            limit 1
          ) confirmation on true
          where coalesce(nullif(bank.status, ''), 'active') <> all(%s::text[])
            and (%s::date is null or bank.txn_date >= %s::date - interval '2 days')
            and (%s::date is null or bank.txn_date <= %s::date + interval '2 days')
        ),
        display_rows as materialized (
          select
            source.*,
            nullif(
              regexp_replace(
                coalesce(
                  source.account_no,
                  source.normalized_payload->>'account_no',
                  ''
                ),
                '[^[:alnum:]]',
                '',
                'g'
              ),
              ''
            ) as normalized_account_no,
            coalesce(
              nullif(source.normalized_payload->>'imported_bank_name', ''),
              nullif(source.normalized_payload->>'bank_name', ''),
              '未知银行'
            ) as bank_name,
            right(
              coalesce(
                nullif(source.normalized_payload->>'imported_bank_last4', ''),
                nullif(source.normalized_payload->>'account_last4', ''),
                nullif(
                  regexp_replace(coalesce(source.account_no, ''), '[^[:alnum:]]', '', 'g'),
                  ''
                ),
                'unknown'
              ),
              4
            ) as account_last4,
            case
              when lower(coalesce(source.txn_direction, '')) in (
                'income', 'credit', 'inflow', '收入', '收'
              ) then 'income'
              when lower(coalesce(source.txn_direction, '')) in (
                'expense', 'debit', 'outflow', '支出', '支'
              ) then 'expense'
              when source.signed_amount >= 0 then 'income'
              else 'expense'
            end as direction,
            coalesce(
              (
                select item->>'value'
                from jsonb_array_elements(
                  case
                    when jsonb_typeof(source.bank_text_fields) = 'array'
                      then source.bank_text_fields
                    else '[]'::jsonb
                  end
                ) item
                where item->>'label' in ('摘要')
                  and nullif(item->>'value', '') is not null
                limit 1
              ),
              source.summary,
              ''
            ) as summary_text,
            coalesce(
              (
                select item->>'value'
                from jsonb_array_elements(
                  case
                    when jsonb_typeof(source.bank_text_fields) = 'array'
                      then source.bank_text_fields
                    else '[]'::jsonb
                  end
                ) item
                where item->>'label' in ('用途', '交易用途')
                  and nullif(item->>'value', '') is not null
                limit 1
              ),
              ''
            ) as purpose_text,
            coalesce(
              (
                select item->>'value'
                from jsonb_array_elements(
                  case
                    when jsonb_typeof(source.bank_text_fields) = 'array'
                      then source.bank_text_fields
                    else '[]'::jsonb
                  end
                ) item
                where item->>'label' in ('备注', '附言', '客户附言')
                  and nullif(item->>'value', '') is not null
                limit 1
              ),
              source.remark,
              ''
            ) as note_text,
            coalesce(
              (
                select string_agg(item->>'value', ' ')
                from jsonb_array_elements(
                  case
                    when jsonb_typeof(source.bank_text_fields) = 'array'
                      then source.bank_text_fields
                    else '[]'::jsonb
                  end
                ) item
                where nullif(item->>'value', '') is not null
              ),
              ''
            ) as detail_text
          from source_rows source
        ),
        base as materialized (
          select
            display.*,
            case
              when normalized_account_no is not null and normalized_account_no <> ''
                then 'acct:' || substring(
                  encode(digest(normalized_account_no, 'sha256'), 'hex')
                  from 1 for 24
                )
              else 'fallback:' || substring(
                encode(
                  digest(
                    lower(btrim(bank_name)) || ':' ||
                    coalesce(nullif(account_last4, ''), 'unknown'),
                    'sha256'
                  ),
                  'hex'
                )
                from 1 for 24
              )
            end as account_key
            {normalization_sql}
          from display_rows display
        ),
        internal_pair_candidates as materialized (
          select
            outgoing.row_id as outgoing_id,
            incoming.row_id as incoming_id,
            round(abs(outgoing.amount), 2) as matched_amount,
            abs(extract(epoch from (
              incoming.trade_time_sort - outgoing.trade_time_sort
            )))::integer as delta_seconds,
            outgoing.account_key as outgoing_account_key,
            incoming.account_key as incoming_account_key,
            (
              concat_ws(
                ' ',
                outgoing.purpose_text,
                outgoing.summary_text,
                outgoing.note_text,
                outgoing.detail_text
              ) ilike any(%s::text[])
            ) as outgoing_explicit,
            (
              concat_ws(
                ' ',
                incoming.purpose_text,
                incoming.summary_text,
                incoming.note_text,
                incoming.detail_text
              ) ilike any(%s::text[])
            ) as incoming_explicit
          from base outgoing
          join base incoming
            on outgoing.direction = 'expense'
           and incoming.direction = 'income'
           and outgoing.account_key <> incoming.account_key
           and round(abs(outgoing.amount), 2) = round(abs(incoming.amount), 2)
           and abs(extract(epoch from (
             incoming.trade_time_sort - outgoing.trade_time_sort
           ))) <= 172800
          where outgoing.counterparty_name_raw ilike any(%s::text[])
            and incoming.counterparty_name_raw ilike any(%s::text[])
            and outgoing.amount > 0
            and incoming.amount > 0
        ),
        internal_pair_degrees as (
          select row_id, count(*)::integer as degree
          from (
            select outgoing_id as row_id from internal_pair_candidates
            union all
            select incoming_id as row_id from internal_pair_candidates
          ) ids
          group by row_id
        ),
        normal_internal_pairs as (
          select candidate.*
          from internal_pair_candidates candidate
          join internal_pair_degrees outgoing
            on outgoing.row_id = candidate.outgoing_id
          join internal_pair_degrees incoming
            on incoming.row_id = candidate.incoming_id
          where outgoing.degree = 1
            and incoming.degree = 1
        ),
        ranked_explicit_pairs as (
          select
            candidate.*,
            row_number() over (
              partition by outgoing_id
              order by delta_seconds, incoming_id
            ) as outgoing_rank,
            row_number() over (
              partition by incoming_id
              order by delta_seconds, outgoing_id
            ) as incoming_rank
          from internal_pair_candidates candidate
          join internal_pair_degrees outgoing
            on outgoing.row_id = candidate.outgoing_id
          join internal_pair_degrees incoming
            on incoming.row_id = candidate.incoming_id
          where (outgoing.degree > 1 or incoming.degree > 1)
            and outgoing_explicit
            and incoming_explicit
        ),
        resolved_internal_pairs as materialized (
          select * from normal_internal_pairs
          union all
          select
            outgoing_id,
            incoming_id,
            matched_amount,
            delta_seconds,
            outgoing_account_key,
            incoming_account_key,
            outgoing_explicit,
            incoming_explicit
          from ranked_explicit_pairs
          where outgoing_rank = 1 and incoming_rank = 1
        ),
        internal_by_row as (
          select
            outgoing_id as row_id,
            incoming_id as counterpart_id,
            matched_amount,
            delta_seconds,
            outgoing_account_key as account_key,
            incoming_account_key as counterpart_account_key
          from resolved_internal_pairs
          union all
          select
            incoming_id,
            outgoing_id,
            matched_amount,
            delta_seconds,
            incoming_account_key,
            outgoing_account_key
          from resolved_internal_pairs
        ),
        rule_matches as materialized (
          select
            base.row_id,
            rule_match.priority,
            rule_match.sort_order,
            rule_match.definition
          from base
          cross join lateral (
            {rule_sql}
          ) rule_match
        ),
        matched_definitions as (
          select
            matches.row_id,
            jsonb_agg(
              matches.definition
              order by matches.sort_order, matches.definition->>'code'
            ) filter (where matches.priority = minimum.priority) as definitions
          from rule_matches matches
          join (
            select row_id, min(priority) as priority
            from rule_matches
            group by row_id
          ) minimum
            on minimum.row_id = matches.row_id
          group by matches.row_id
        ),
        classified as materialized (
          select
            base.*,
            internal.counterpart_id,
            internal.matched_amount as internal_matched_amount,
            internal.delta_seconds as internal_delta_seconds,
            internal.counterpart_account_key,
            counterpart.trade_time as counterpart_trade_time,
            counterpart.txn_date as counterpart_trade_date,
            counterpart.bank_name as counterpart_bank_name,
            counterpart.account_last4 as counterpart_account_last4,
            counterpart.amount as counterpart_amount,
            counterpart.direction as counterpart_direction,
            counterpart.counterparty_name_raw as counterpart_name,
            coalesce(matches.definitions, '[]'::jsonb) as matched_definitions,
            case
              when internal.row_id is not null then 'internal_transfer'
              when jsonb_array_length(coalesce(matches.definitions, '[]'::jsonb)) = 1
               and not (
                 coalesce(matches.definitions->0->>'turnover_role', '') = 'external_turnover'
                 and coalesce(matches.definitions->0->>'output_third_label', '') = ''
               )
                then matches.definitions->0->>'code'
              else null
            end as auto_category_code,
            case
              when internal.row_id is not null then 'internal_transfer'
              when jsonb_array_length(coalesce(matches.definitions, '[]'::jsonb)) = 0
                then 'unmatched'
              when jsonb_array_length(coalesce(matches.definitions, '[]'::jsonb)) = 1
               and not (
                 coalesce(matches.definitions->0->>'turnover_role', '') = 'external_turnover'
                 and coalesce(matches.definitions->0->>'output_third_label', '') = ''
               )
                then 'auto_matched'
              else 'needs_confirmation'
            end as auto_resolution_status
          from base
          left join internal_by_row internal on internal.row_id = base.row_id
          left join base counterpart on counterpart.row_id = internal.counterpart_id
          left join matched_definitions matches on matches.row_id = base.row_id
        ),
        effective as materialized (
          select
            classified.*,
            case
              when confirmation_id is not null then confirmed_category_code
              when manual_category_code is not null
               and manual_category_source = 'manual'
               and coalesce(
                 manual_category_raw_payload->'normalized_payload'->>'manual_assignment',
                 manual_category_raw_payload->>'manual_assignment',
                 'false'
               ) = 'true'
               and auto_category_code is null
                then manual_category_code
              when manual_category_code is not null
               and (
                 manual_category_source = 'turnover_ledger'
                 or auto_category_code = 'external_turnover'
               )
                then manual_category_code
              else auto_category_code
            end as effective_category_code,
            case
              when confirmation_id is not null then 'manual_confirmation'
              when manual_category_code is not null
               and manual_category_source = 'manual'
               and coalesce(
                 manual_category_raw_payload->'normalized_payload'->>'manual_assignment',
                 manual_category_raw_payload->>'manual_assignment',
                 'false'
               ) = 'true'
               and auto_category_code is null
                then 'manual'
              when manual_category_code is not null
               and (
                 manual_category_source = 'turnover_ledger'
                 or auto_category_code = 'external_turnover'
               )
                then manual_category_source
              when auto_category_code is not null then 'auto'
              else ''
            end as effective_category_source
          from classified
        ),
        classified_with_semantics as materialized (
          select
            effective.*,
            definition.definition as effective_definition,
            coalesce(
              confirmation_raw_payload->'normalized_payload'->>'category_primary_label',
              manual_category_raw_payload->'normalized_payload'->>'category_primary_label',
              definition.definition->>'output_primary_label',
              definition.definition->>'category_primary_label'
            ) as effective_category_primary_label,
            coalesce(
              confirmation_raw_payload->'normalized_payload'->>'category_sub_label',
              manual_category_raw_payload->'normalized_payload'->>'category_sub_label',
              definition.definition->>'output_sub_label',
              definition.definition->>'category_sub_label'
            ) as effective_category_sub_label,
            coalesce(
              confirmation_raw_payload->'normalized_payload'->>'category_third_label',
              manual_category_raw_payload->'normalized_payload'->>'category_third_label',
              definition.definition->>'output_third_label',
              definition.definition->>'category_third_label'
            ) as effective_category_third_label,
            coalesce(
              confirmation_raw_payload->'normalized_payload'->>'category_label',
              manual_category_raw_payload->'normalized_payload'->>'category_label',
              definition.definition->>'label'
            ) as effective_category_label
          from effective
          left join tag_definitions definition
            on definition.definition->>'code' = effective.effective_category_code
        )
        """,
        params,
    )


def _validate_date_range(
    *,
    date_from: str | None,
    date_to: str | None,
) -> None:
    try:
        parsed_from = date.fromisoformat(date_from) if date_from else None
        parsed_to = date.fromisoformat(date_to) if date_to else None
    except ValueError as exc:
        raise ValueError("date_from 和 date_to 必须是 YYYY-MM-DD。") from exc
    if parsed_from is not None and parsed_to is not None and parsed_from > parsed_to:
        raise ValueError("date_from 不能晚于 date_to。")


def _validate_pagination(*, page: int, page_size: int) -> None:
    if page < 1:
        raise ValueError("page 必须大于等于 1。")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise ValueError(f"page_size 必须在 1 到 {MAX_PAGE_SIZE} 之间。")


def _rule_match_union_sql(
    definitions: list[dict[str, Any]],
) -> tuple[str, list[Any]]:
    statements: list[str] = []
    params: list[Any] = []
    for definition in definitions:
        if str(definition.get("status") or "active") != "active":
            continue
        rules = definition.get("rules")
        if not isinstance(rules, dict):
            continue
        predicate, predicate_params = _rule_predicate(definition)
        if predicate == "false":
            continue
        try:
            priority = max(int(definition.get("priority") or 2), 2)
        except (TypeError, ValueError):
            priority = 2
        try:
            sort_order = max(int(definition.get("sort_order") or 10_000), 0)
        except (TypeError, ValueError):
            sort_order = 10_000
        statements.append(
            f"""
            select %s::integer as priority,
                   %s::integer as sort_order,
                   %s::jsonb as definition
            where {predicate}
            """
        )
        params.extend(
            [
                priority,
                sort_order,
                json.dumps(
                    definition,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                *predicate_params,
            ]
        )
    if not statements:
        return (
            """
            select null::integer as priority,
                   null::integer as sort_order,
                   null::jsonb as definition
            where false
            """,
            [],
        )
    return "\nunion all\n".join(statements), params


def _normalization_select_sql(definitions: list[dict[str, Any]]) -> str:
    normalized_fields: set[str] = set()
    regex_fields: set[str] = set()
    for definition in definitions:
        if str(definition.get("status") or "active") != "active":
            continue
        rules = definition.get("rules")
        if not isinstance(rules, dict):
            continue
        fields = {
            str(field)
            for field in list(rules.get("match_fields") or [])
            if str(field) in _MATCH_FIELD_EXPRESSIONS or str(field) == "all_text"
        }
        expanded = (
            set(_MATCH_FIELD_EXPRESSIONS)
            if "all_text" in fields
            else fields
        )
        if any(
            rules.get(key)
            for key in (
                "exact_any",
                "exact",
                "contains_any",
                "contains",
                "contains_all",
                "none_of",
                "excludes",
            )
        ):
            normalized_fields.update(expanded)
        if rules.get("regex_any"):
            regex_fields.update(expanded)
        scope = (
            definition.get("account_scope")
            if isinstance(definition.get("account_scope"), dict)
            else {}
        )
        if list(scope.get("values") or []):
            scope_field = {
                "bank_account": "account_no",
                "account_type": "account_type",
                "bank": "bank_name",
            }.get(str(scope.get("type") or ""))
            if scope_field:
                normalized_fields.add(scope_field)
    columns = [
        f", {_normalized_sql(_MATCH_FIELD_EXPRESSIONS[field][0])} "
        f"as {_MATCH_FIELD_EXPRESSIONS[field][1]}"
        for field in sorted(normalized_fields)
    ]
    columns.extend(
        f", {_regex_normalized_sql(_MATCH_FIELD_EXPRESSIONS[field][0])} "
        f"as {_MATCH_FIELD_EXPRESSIONS[field][2]}"
        for field in sorted(regex_fields)
    )
    return "\n".join(columns)


def _rule_predicate(definition: dict[str, Any]) -> tuple[str, list[Any]]:
    rules = definition.get("rules")
    if not isinstance(rules, dict):
        return "false", []
    field_names = [
        str(field)
        for field in list(rules.get("match_fields") or [])
        if str(field) in _NORMALIZED_FIELD_SQL
    ]
    if not field_names:
        return "false", []
    normalized_fields = [_NORMALIZED_FIELD_SQL[field] for field in field_names]
    regex_fields = [_REGEX_FIELD_SQL[field] for field in field_names]
    clauses: list[str] = []
    params: list[Any] = []

    direction = str(definition.get("direction") or "any").strip()
    if direction not in {"", "any"}:
        clauses.append("base.direction = %s")
        params.append(direction)

    scope = (
        definition.get("account_scope")
        if isinstance(definition.get("account_scope"), dict)
        else {}
    )
    scope_type = str(scope.get("type") or "any")
    scope_values = [
        BankTransactionAutoCategoryService._normalize_match_text(value)
        for value in list(scope.get("values") or [])
        if str(value)
    ]
    if scope_values:
        if scope_type == "bank_account":
            clauses.append(
                "(base.norm_account_no = any(%s::text[]) "
                "or lower(base.account_key) = any(%s::text[]))"
            )
            params.extend([scope_values, scope_values])
        elif scope_type == "account_type":
            clauses.append("base.norm_account_type = any(%s::text[])")
            params.append(scope_values)
        elif scope_type == "bank":
            clauses.append("base.norm_bank_name = any(%s::text[])")
            params.append(scope_values)

    none_of = [
        BankTransactionAutoCategoryService._normalize_match_text(value)
        for value in list(rules.get("none_of") or rules.get("excludes") or [])
        if str(value)
    ]
    for token in none_of:
        clauses.append(
            "not (" + " or ".join(f"strpos({field}, %s) > 0" for field in normalized_fields) + ")"
        )
        params.extend([token] * len(normalized_fields))

    contains_all = [
        BankTransactionAutoCategoryService._normalize_match_text(value)
        for value in list(rules.get("contains_all") or [])
        if str(value)
    ]
    joined_fields = " || ".join(f"coalesce({field}, '')" for field in normalized_fields)
    for token in contains_all:
        clauses.append(f"strpos(({joined_fields}), %s) > 0")
        params.append(token)

    positive: list[str] = []
    for value in list(rules.get("exact_any") or rules.get("exact") or []):
        token = BankTransactionAutoCategoryService._normalize_match_text(value)
        if not token:
            continue
        positive.append(
            "(" + " or ".join(f"{field} = %s" for field in normalized_fields) + ")"
        )
        params.extend([token] * len(normalized_fields))
    for value in list(rules.get("contains_any") or rules.get("contains") or []):
        token = BankTransactionAutoCategoryService._normalize_match_text(value)
        if not token:
            continue
        positive.append(
            "(" + " or ".join(f"strpos({field}, %s) > 0" for field in normalized_fields) + ")"
        )
        params.extend([token] * len(normalized_fields))
    for pattern in list(rules.get("regex_any") or []):
        if not str(pattern):
            continue
        positive.append(
            "(" + " or ".join(f"{field} ~* %s" for field in regex_fields) + ")"
        )
        params.extend([str(pattern)] * len(regex_fields))
    if contains_all:
        positive.append("true")
    if not positive:
        return "false", []
    clauses.append("(" + " or ".join(positive) + ")")
    return " and ".join(clauses) if clauses else "true", params


_MATCH_FIELD_EXPRESSIONS = {
    "counterparty_name": (
        "counterparty_name_raw",
        "norm_counterparty_name",
        "regex_counterparty_name",
    ),
    "counterparty_account": (
        "normalized_payload->>'counterparty_account'",
        "norm_counterparty_account",
        "regex_counterparty_account",
    ),
    "counterparty_bank": (
        "normalized_payload->>'counterparty_bank'",
        "norm_counterparty_bank",
        "regex_counterparty_bank",
    ),
    "purpose_text": ("purpose_text", "norm_purpose_text", "regex_purpose_text"),
    "summary_text": ("summary_text", "norm_summary_text", "regex_summary_text"),
    "note_text": ("note_text", "norm_note_text", "regex_note_text"),
    "detail_text": ("detail_text", "norm_detail_text", "regex_detail_text"),
    "account_no": ("account_no", "norm_account_no", "regex_account_no"),
    "account_type": (
        "normalized_payload->>'account_type'",
        "norm_account_type",
        "regex_account_type",
    ),
    "bank_name": ("bank_name", "norm_bank_name", "regex_bank_name"),
}

_NORMALIZED_FIELD_SQL = {
    "counterparty_name": "base.norm_counterparty_name",
    "counterparty_account": "base.norm_counterparty_account",
    "counterparty_bank": "base.norm_counterparty_bank",
    "purpose_text": "base.norm_purpose_text",
    "summary_text": "base.norm_summary_text",
    "note_text": "base.norm_note_text",
    "detail_text": "base.norm_detail_text",
    "all_text": (
        "base.norm_counterparty_name || base.norm_counterparty_account || "
        "base.norm_counterparty_bank || base.norm_purpose_text || "
        "base.norm_summary_text || base.norm_note_text || base.norm_detail_text"
    ),
}
_REGEX_FIELD_SQL = {
    "counterparty_name": "base.regex_counterparty_name",
    "counterparty_account": "base.regex_counterparty_account",
    "counterparty_bank": "base.regex_counterparty_bank",
    "purpose_text": "base.regex_purpose_text",
    "summary_text": "base.regex_summary_text",
    "note_text": "base.regex_note_text",
    "detail_text": "base.regex_detail_text",
    "all_text": (
        "base.regex_counterparty_name || ' ' || base.regex_counterparty_account || ' ' || "
        "base.regex_counterparty_bank || ' ' || base.regex_purpose_text || ' ' || "
        "base.regex_summary_text || ' ' || base.regex_note_text || ' ' || base.regex_detail_text"
    ),
}


def _normalized_sql(expression: str) -> str:
    return (
        "lower(regexp_replace("
        f"replace(replace(replace(normalize(coalesce({expression}, ''), NFKC), "
        "'帐户', '账户'), '（', '('), '）', ')'), "
        "'[[:space:]]+', '', 'g'))"
    )


def _regex_normalized_sql(expression: str) -> str:
    return (
        "lower(regexp_replace("
        f"replace(replace(replace(normalize(coalesce({expression}, ''), NFKC), "
        "'帐户', '账户'), '（', '('), '）', ')'), "
        "'[[:space:]]+', ' ', 'g'))"
    )


def _transaction_filter_sql(
    *,
    account_key: str | None,
    date_from: str | None,
    date_to: str | None,
    keyword: str | None,
    category_code: str | None,
    category_primary_label: str | None,
    category_sub_label: str | None,
    category_third_label: str | None,
) -> tuple[str, list[Any]]:
    clauses = [
        "(%s::text is null or account_key = %s)",
        "(%s::date is null or txn_date >= %s::date)",
        "(%s::date is null or txn_date <= %s::date)",
    ]
    params: list[Any] = [
        account_key,
        account_key,
        date_from,
        date_from,
        date_to,
        date_to,
    ]
    normalized_keyword = str(keyword or "").strip().lower()
    if normalized_keyword:
        clauses.append(
            """
            lower(concat_ws(
              ' ',
              counterparty_name_raw,
              trade_time::text,
              case when direction = 'income' then '收' else '支' end,
              amount::text,
              balance::text,
              summary_text,
              purpose_text,
              note_text,
              bank_name,
              account_last4,
              effective_category_label,
              effective_category_primary_label,
              effective_category_sub_label,
              effective_category_third_label
            )) like %s
            """
        )
        params.append(f"%{normalized_keyword}%")
    normalized_category_code = str(category_code or "").strip()
    if normalized_category_code:
        if normalized_category_code == "uncategorized":
            clauses.append("effective_category_code is null")
        else:
            clauses.append("effective_category_code = %s")
            params.append(normalized_category_code)
    for column, value in (
        ("effective_category_primary_label", category_primary_label),
        ("effective_category_sub_label", category_sub_label),
        ("effective_category_third_label", category_third_label),
    ):
        normalized_value = str(value or "").strip()
        if normalized_value:
            clauses.append(f"{column} = %s")
            params.append(normalized_value)
    return " and ".join(clauses), params


def _without_summary_columns(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if not key.startswith("result_")
    }


def _transaction_relation_lookup_ids(rows: list[dict[str, Any]]) -> list[str]:
    return text_list(
        [
            identity
            for row in rows
            for identity in (
                row.get("row_id"),
                row.get("canonical_transaction_id"),
            )
        ]
    )


def _relation_payloads_by_row_id(
    relation_rows: list[dict[str, Any]],
    transaction_rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    alias_to_row_id: dict[str, str] = {}
    for row in transaction_rows:
        if not isinstance(row, dict):
            continue
        target = text(row.get("row_id"))
        if not target:
            continue
        for identity in (target, text(row.get("canonical_transaction_id"))):
            if identity:
                alias_to_row_id[identity] = target
    result: dict[str, dict[str, Any]] = {}
    for relation in relation_rows:
        if not isinstance(relation, dict):
            continue
        row_ids = text_list(relation.get("row_ids"))
        row_types = text_list(relation.get("row_types"))
        normalized_types = {
            (
                row_types[index]
                if index < len(row_types) and row_types[index]
                else row_type_for_workbench_row_id(row_id, unknown="")
            )
            for index, row_id in enumerate(row_ids)
        }
        bank_ids = {
            alias_to_row_id[row_id]
            for row_id in row_ids
            if row_id in alias_to_row_id
        }
        for bank_id in bank_ids:
            payload = result.setdefault(
                bank_id,
                {"row_types": [], "case_id": text(relation.get("case_id"))},
            )
            payload["row_types"] = sorted(
                set(text_list(payload.get("row_types"))).union(normalized_types)
            )
            payload["case_id"] = payload.get("case_id") or text(
                relation.get("case_id")
            )
    return result


def _manual_category_payload(
    row: dict[str, Any],
    *,
    category_service: BankTransactionCategoryService,
) -> dict[str, Any]:
    confirmed = bool(row.get("confirmation_id"))
    category_code = text(
        row.get("confirmed_category_code")
        if confirmed
        else row.get("manual_category_code")
    )
    source = (
        "auto_confirmation"
        if confirmed
        else text(row.get("manual_category_source")) or ""
    )
    raw_payload = (
        row.get("confirmation_raw_payload")
        if confirmed
        else row.get("manual_category_raw_payload")
    )
    raw_payload = raw_payload if isinstance(raw_payload, dict) else {}
    normalized = (
        raw_payload.get("normalized_payload")
        if isinstance(raw_payload.get("normalized_payload"), dict)
        else raw_payload
    )
    semantics = category_service.category_semantics_for_code(category_code or "")
    return {
        "category_code": category_code,
        "category_label": (
            text(normalized.get("category_label"))
            or text(semantics.get("category_label"))
        ),
        "category_path": (
            text_list(normalized.get("category_path"))
            or list(semantics.get("category_path") or [])
        ),
        "category_primary_label": (
            text(normalized.get("category_primary_label"))
            or text(semantics.get("category_primary_label"))
        ),
        "category_sub_label": (
            text(normalized.get("category_sub_label"))
            or text(semantics.get("category_sub_label"))
        ),
        "category_third_label": (
            text(normalized.get("category_third_label"))
            or text(semantics.get("category_third_label"))
        ),
        "category_label_path": (
            text_list(normalized.get("category_label_path"))
            or list(semantics.get("category_label_path") or [])
        ),
        "turnover_role": (
            text(normalized.get("turnover_role"))
            or text(semantics.get("turnover_role"))
        ),
        "turnover_action_type": (
            text(normalized.get("turnover_action_type"))
            or text(semantics.get("turnover_action_type"))
        ),
        "turnover_family": (
            text(normalized.get("turnover_family"))
            or text(semantics.get("turnover_family"))
        ),
        "source": source,
        "category_version": int_value(
            row.get("confirmation_version")
            if confirmed
            else row.get("manual_category_version"),
            0,
        ),
        "category_rule_version": (
            text(row.get("confirmation_rule_version"))
            or text(normalized.get("category_rule_version"))
        ),
        "manual_assignment": bool(normalized.get("manual_assignment")),
    }


def _auto_category_payload(
    row: dict[str, Any],
    *,
    category_service: BankTransactionCategoryService,
    auto_service: BankTransactionAutoCategoryService,
) -> dict[str, Any] | None:
    if text(row.get("auto_resolution_status")) == "internal_transfer":
        semantics = category_service.category_semantics_for_code(
            "internal_transfer"
        )
        counterpart_id = text(row.get("counterpart_id")) or ""
        auto = {
            "transaction_id": text(row.get("row_id")) or "",
            "counterpart_id": counterpart_id,
            "counterpart_account_key": text(row.get("counterpart_account_key")),
            "match_delta_seconds": int_value(row.get("internal_delta_seconds"), 0),
            "matched_amount": decimal_text(row.get("internal_matched_amount")),
            "category_code": "internal_transfer",
            "category_label": (
                text(semantics.get("category_label")) or "内部往来款"
            ),
            "category_path": (
                list(semantics.get("category_path") or [])
                or ["自动识别", "内部往来款"]
            ),
            "category_primary_label": text(
                semantics.get("category_primary_label")
            ),
            "category_sub_label": text(semantics.get("category_sub_label")),
            "category_third_label": text(
                semantics.get("category_third_label")
            ),
            "category_label_path": list(
                semantics.get("category_label_path") or []
            ),
            "source": "auto",
            "rule_code": "internal_transfer_pair",
            "reason": (
                f"内部往来配对：金额 {decimal_text(row.get('internal_matched_amount')) or '0.00'}，"
                f"对方流水 {counterpart_id}"
            ),
            "confidence": "high",
            "rule_version": auto_service.current_rule_version(),
            "category_resolution_status": "internal_transfer",
            "auto_category_code": "internal_transfer",
            "internal_transfer_counterpart": {
                "transaction_id": counterpart_id,
                "trade_time": text(
                    row.get("counterpart_trade_time")
                    or row.get("counterpart_trade_date")
                )
                or "",
                "bank_name": text(row.get("counterpart_bank_name"))
                or "未知银行",
                "account_last4": text(
                    row.get("counterpart_account_last4")
                )
                or "unknown",
                "amount": decimal_text(row.get("counterpart_amount")) or "0.00",
                "direction_label": (
                    "收"
                    if text(row.get("counterpart_direction")) == "income"
                    else "支"
                ),
                "counterparty_name": text(row.get("counterpart_name")) or "",
            },
        }
        auto["auto_candidate_category_codes"] = ["internal_transfer"]
        auto["auto_candidate_categories"] = [
            {
                "transaction_id": auto["transaction_id"],
                "category_code": "internal_transfer",
                "category_label": auto["category_label"],
                "category_primary_label": auto["category_primary_label"],
                "category_sub_label": auto["category_sub_label"],
                "category_third_label": auto["category_third_label"],
                "category_label_path": auto["category_label_path"],
                "category_path": auto["category_path"],
                "source": "auto",
                "rule_code": auto["rule_code"],
                "reason": auto["reason"],
                "confidence": "high",
                "rule_version": auto["rule_version"],
            }
        ]
        return auto
    definitions = [
        dict(definition)
        for definition in list(row.get("matched_definitions") or [])
        if isinstance(definition, dict)
    ]
    return auto_service.suggestion_for_rule_matches(
        text(row.get("row_id")) or "",
        definitions,
    )
