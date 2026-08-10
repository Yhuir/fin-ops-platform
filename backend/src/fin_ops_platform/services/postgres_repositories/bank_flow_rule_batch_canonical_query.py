from __future__ import annotations

from calendar import monthrange
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.bank_details_canonical_query import (
    bank_category_classification_cte,
)
from fin_ops_platform.services.postgres_repositories.common import int_value, month_start, row_payload, text, text_list

_CLASSIFIED_CANDIDATE_ROWS_SQL = """
    select
        candidate.canonical_transaction_id as id,
        candidate.row_id as transaction_id,
        candidate.account_no,
        candidate.direction as txn_direction,
        candidate.normalized_counterparty_name,
        candidate.counterparty_name_raw,
        candidate.amount,
        candidate.txn_date,
        candidate.trade_time,
        candidate.pay_receive_time,
        candidate.summary_text as summary,
        candidate.purpose_text as purpose,
        candidate.note_text as remark,
        candidate.bank_name,
        candidate.account_last4,
        coalesce(
            nullif(candidate.normalized_payload->>'account_key', ''),
            candidate.bank_name || ':' || candidate.account_last4
        ) as account_key,
        candidate.effective_category_code as category_code,
        candidate.effective_category_source as category_source,
        coalesce(
            candidate.confirmation_version,
            candidate.manual_category_version,
            0
        )::integer as category_version,
        'canonical_sql'::text as category_resolution_authority
    from classified_with_semantics candidate
"""
_CLASSIFIED_SCOPED_CANDIDATE_ROWS_SQL = _CLASSIFIED_CANDIDATE_ROWS_SQL + """
    where coalesce(candidate.txn_date, candidate.txn_month) >= %s::date - interval '2 days'
      and coalesce(candidate.txn_date, candidate.txn_month) <= %s::date + interval '2 days'
"""


class BankFlowRuleBatchCanonicalQueryRepository:
    """Page query boundary backed only by PostgreSQL canonical facts."""

    def __init__(self, connection: Any) -> None:
        if connection is None or not callable(getattr(connection, "transaction", None)):
            raise ValueError("Bank flow rule batch canonical queries require a PostgreSQL connection.")
        self._connection = connection

    def read_page(
        self,
        filters: dict[str, object] | None = None,
        *,
        summary_filters: dict[str, object] | None = None,
        page: int = 1,
        page_size: int | None = 50,
    ) -> dict[str, object]:
        _ = max(int_value(page, 1), 1)
        _ = None if page_size is None else min(max(int_value(page_size, 50), 1), 200)
        self._filters_sql(filters)
        self._filters_sql(summary_filters)
        resolved_filters = filters if isinstance(filters, dict) else {}
        resolved_summary_filters = summary_filters if isinstance(summary_filters, dict) else {}
        source_month = text(
            resolved_summary_filters.get("month") or resolved_filters.get("month")
        )
        source_account_key = text(
            resolved_summary_filters.get("account_key")
            or resolved_filters.get("account_key")
        )
        formal_scope_sql = ""
        formal_scope_params: list[object] = []
        if source_month:
            scope_start = month_start(source_month)
            formal_scope_sql += " and batch.scope_month = %s::date"
            formal_scope_params.append(scope_start)
        if source_account_key:
            formal_scope_sql += " and batch.account_key = %s"
            formal_scope_params.append(source_account_key)
        with self._snapshot() as transaction:
            tag_sources = self._tag_sources(transaction)
            tag_policy = tag_sources["tag_policy"]
            tag_dictionary = tag_sources["tag_dictionary"]
            definitions = [
                dict(definition)
                for definition in list(tag_dictionary.get("definitions") or [])
                if isinstance(definition, dict)
            ]
            scope_start = (
                date.fromisoformat(month_start(source_month)) if source_month else None
            )
            scope_end = (
                date(
                    scope_start.year,
                    scope_start.month,
                    monthrange(scope_start.year, scope_start.month)[1],
                )
                if scope_start is not None
                else None
            )
            classification_sql, classification_params = bank_category_classification_cte(
                definitions=definitions,
                date_from=None,
                date_to=None,
                defer_full_payload=True,
            )
            candidate_rows_sql = (
                _CLASSIFIED_SCOPED_CANDIDATE_ROWS_SQL
                if scope_start is not None and scope_end is not None
                else _CLASSIFIED_CANDIDATE_ROWS_SQL
            )
            candidate_scope_params = (
                [scope_start.isoformat(), scope_end.isoformat()]
                if scope_start is not None and scope_end is not None
                else []
            )
            transaction.execute("set local jit = off")
            source_result = transaction.fetch_one(
                f"""
                with {classification_sql},
                bank_source as materialized (
                    {candidate_rows_sql}
                ),
                bank_identities as materialized (
                    select bank.id as bank_id, bank.transaction_id as identity
                    from bank_source bank
                    union
                    select bank.id as bank_id, bank.id as identity
                    from bank_source bank
                ),
                candidate_rows as materialized (
                    select bank.*
                    from bank_source bank
                ),
                candidate_identity_array as materialized (
                    select array_agg(identity order by identity) as row_ids
                    from bank_identities
                ),
                active_relations as materialized (
                    select relation.*
                    from app.workbench_pair_relations relation
                    cross join candidate_identity_array candidate_ids
                    where relation.status = 'active'
                      and candidate_ids.row_ids is not null
                      and relation.row_ids && candidate_ids.row_ids
                ),
                formal_items as materialized (
                    select
                        batch.*,
                        coalesce(
                            batch.raw_payload->'normalized_payload',
                            '{{}}'::jsonb
                        ) as payload,
                        exists (
                            select 1
                            from app.workbench_pair_relations relation
                            where relation.status = 'active'
                              and relation.case_id = coalesce(
                                  nullif(
                                      batch.raw_payload->'normalized_payload'
                                          ->>'relation_case_id',
                                      ''
                                  ),
                                  batch.batch_id
                              )
                        ) as has_active_relation
                    from app.bank_flow_rule_batches batch
                    where (
                        batch.status in ('submitted', 'withdrawn')
                        or (
                            batch.status = 'stale'
                            and exists (
                                select 1
                                from app.workbench_pair_relations relation
                                where relation.status = 'active'
                                  and relation.case_id = coalesce(
                                      nullif(
                                          batch.raw_payload->'normalized_payload'
                                              ->>'relation_case_id',
                                          ''
                                      ),
                                      batch.batch_id
                                  )
                            )
                        )
                    )
                    {formal_scope_sql}
                )
                select
                    coalesce(
                        (
                            select jsonb_agg(
                                to_jsonb(candidate)
                                order by candidate.txn_date, candidate.transaction_id
                            )
                            from candidate_rows candidate
                        ),
                        '[]'::jsonb
                    ) as candidate_rows,
                    coalesce(
                        (
                            select jsonb_agg(to_jsonb(relation) order by relation.case_id)
                            from active_relations relation
                        ),
                        '[]'::jsonb
                    ) as active_relations,
                    coalesce(
                        (
                            select jsonb_agg(
                                to_jsonb(batch)
                                order by batch.scope_month, batch.batch_id
                            )
                            from formal_items batch
                        ),
                        '[]'::jsonb
                    ) as formal_items
                """,
                tuple(
                    [
                        *classification_params,
                        *candidate_scope_params,
                        *formal_scope_params,
                    ]
                ),
            ) or {}
        candidate_rows = source_result.get("candidate_rows")
        candidate_rows = candidate_rows if isinstance(candidate_rows, list) else []
        active_relations = source_result.get("active_relations")
        active_relations = active_relations if isinstance(active_relations, list) else []
        formal_items = source_result.get("formal_items")
        formal_items = formal_items if isinstance(formal_items, list) else []
        return {
            "candidate_rows": [
                self._bank_row_payload(row)
                for row in candidate_rows
                if isinstance(row, dict)
            ],
            "active_relations": [
                dict(row) for row in active_relations if isinstance(row, dict)
            ],
            "formal_items": [
                self._batch_payload(row) for row in formal_items if isinstance(row, dict)
            ],
            "tag_policy": tag_policy,
            "tag_dictionary": tag_sources["tag_dictionary"],
        }

    @classmethod
    def candidate_scope_months(cls, transaction: Any) -> list[str]:
        tag_policy = cls._tag_policy(transaction)
        eligible_codes = cls._eligible_codes(tag_policy)
        if not eligible_codes:
            return []
        rows = transaction.fetch_all(
            """
            /* check: bank_flow_live_candidate_scopes */
            select to_char(
                       coalesce(bank.txn_month, date_trunc('month', bank.txn_date)::date),
                       'YYYY-MM'
                   ) as scope_month
            from app.bank_transactions bank
            where bank.status <> 'deleted'
            group by coalesce(bank.txn_month, date_trunc('month', bank.txn_date)::date)
            order by coalesce(bank.txn_month, date_trunc('month', bank.txn_date)::date)
            """
        )
        return [
            scope_month
            for row in rows
            if (scope_month := text(row.get("scope_month")))
        ]

    @classmethod
    def read_candidate_guard_source(
        cls,
        transaction: Any,
        *,
        scope_month: str,
    ) -> dict[str, object]:
        scope_start = date.fromisoformat(month_start(text(scope_month)))
        scope_end = date(
            scope_start.year,
            scope_start.month,
            monthrange(scope_start.year, scope_start.month)[1],
        )
        tag_sources = cls._tag_sources(transaction)
        tag_policy = tag_sources["tag_policy"]
        tag_dictionary = tag_sources["tag_dictionary"]
        definitions = [
            dict(definition)
            for definition in list(tag_dictionary.get("definitions") or [])
            if isinstance(definition, dict)
        ]
        classification_sql, classification_params = bank_category_classification_cte(
            definitions=definitions,
            date_from=None,
            date_to=None,
            defer_full_payload=True,
        )
        transaction.execute("set local jit = off")
        result = transaction.fetch_one(
            f"""
            with {classification_sql},
            candidate_rows as materialized (
                {_CLASSIFIED_SCOPED_CANDIDATE_ROWS_SQL}
            ),
            candidate_identities as materialized (
                select candidate.transaction_id as identity
                from candidate_rows candidate
                union
                select candidate.id as identity
                from candidate_rows candidate
            ),
            candidate_identity_array as materialized (
                select array_agg(identity order by identity) as row_ids
                from candidate_identities
            ),
            active_relations as materialized (
                select relation.*
                from app.workbench_pair_relations relation
                cross join candidate_identity_array candidate_ids
                where relation.status = 'active'
                  and candidate_ids.row_ids is not null
                  and relation.row_ids && candidate_ids.row_ids
            )
            select
                coalesce(
                    (
                        select jsonb_agg(
                            to_jsonb(candidate)
                            order by candidate.txn_date, candidate.transaction_id
                        )
                        from candidate_rows candidate
                    ),
                    '[]'::jsonb
                ) as candidate_rows,
                coalesce(
                    (
                        select jsonb_agg(to_jsonb(relation) order by relation.case_id)
                        from active_relations relation
                    ),
                    '[]'::jsonb
                ) as active_relations
            """,
            tuple(
                [
                    *classification_params,
                    scope_start.isoformat(),
                    scope_end.isoformat(),
                ]
            ),
        ) or {}
        candidate_rows = result.get("candidate_rows")
        active_relations = result.get("active_relations")
        return {
            "candidate_rows": (
                [
                    cls._bank_row_payload(row)
                    for row in candidate_rows
                    if isinstance(row, dict)
                ]
                if isinstance(candidate_rows, list)
                else []
            ),
            "active_relations": (
                [
                    dict(row)
                    for row in active_relations
                    if isinstance(row, dict)
                ]
                if isinstance(active_relations, list)
                else []
            ),
            "formal_items": [],
            "tag_policy": tag_policy,
            "tag_dictionary": tag_sources["tag_dictionary"],
        }

    def read_detail(self, batch_id: str) -> dict[str, object] | None:
        normalized_batch_id = text(batch_id)
        if not normalized_batch_id:
            return None
        with self._snapshot() as transaction:
            tag_sources = self._tag_sources(transaction)
            tag_policy = tag_sources["tag_policy"]
            batch_row = transaction.fetch_one(
                """
                select
                    batch.*,
                    coalesce(batch.raw_payload->'normalized_payload', '{}'::jsonb) as payload,
                    exists (
                        select 1
                        from app.workbench_pair_relations relation
                        where relation.status = 'active'
                          and relation.case_id = coalesce(
                              nullif(batch.raw_payload->'normalized_payload'->>'relation_case_id', ''),
                              batch.batch_id
                          )
                    ) as has_active_relation
                from app.bank_flow_rule_batches batch
                where batch.batch_id = %s
                  and batch.status in ('submitted', 'withdrawn', 'stale')
                limit 1
                """,
                (normalized_batch_id,),
            )
            if not isinstance(batch_row, dict):
                return None
            batch = self._batch_payload(batch_row)
            row_ids = text_list(batch_row.get("bank_transaction_ids"))
            bank_rows = transaction.fetch_all(
                """
                select
                    bank.*,
                    coalesce(bank.legacy_mongo_id, bank.id::text) as transaction_id,
                    coalesce(bank.raw_payload->'normalized_payload', '{}'::jsonb) as payload,
                    coalesce(confirmed_category.category_code, manual_category.category, '') as category_code,
                    case
                        when confirmed_category.category_code is not null then 'auto_confirmation'
                        else coalesce(manual_category.source, '')
                    end as category_source,
                    coalesce(
                        confirmed_category.version,
                        manual_category.version,
                        0
                    )::integer as category_version,
                    coalesce(active_relations.case_ids, array[]::text[]) as relation_case_ids,
                    coalesce(active_relations.linked_oa_count, 0)::integer as linked_oa_count,
                    coalesce(active_relations.linked_invoice_count, 0)::integer as linked_invoice_count
                from app.bank_transactions bank
                left join lateral (
                    select confirmation.category_code, confirmation.version
                    from app.bank_transaction_category_confirmations confirmation
                    where confirmation.tenant_id = 'default'
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
                ) confirmed_category on true
                left join lateral (
                    select manual.category, manual.source, manual.version
                    from app.bank_transaction_categories manual
                    where manual.status = 'active'
                      and (
                          manual.bank_transaction_id = bank.id
                          or manual.legacy_transaction_id in (
                              coalesce(bank.legacy_mongo_id, bank.id::text),
                              bank.id::text
                          )
                      )
                    order by manual.updated_at desc, manual.id desc
                    limit 1
                ) manual_category on true
                left join lateral (
                    select
                        array_agg(distinct relation.case_id order by relation.case_id) as case_ids,
                        count(distinct member.row_id) filter (
                            where lower(member.row_type) in ('oa', 'oa_application')
                        ) as linked_oa_count,
                        count(distinct member.row_id) filter (
                            where lower(member.row_type) in (
                                'invoice',
                                'input_invoice',
                                'output_invoice'
                            )
                        ) as linked_invoice_count
                    from app.workbench_pair_relations relation
                    cross join lateral unnest(relation.row_ids, relation.row_types) member(row_id, row_type)
                    where relation.status = 'active'
                      and (
                          coalesce(bank.legacy_mongo_id, bank.id::text) = any(relation.row_ids)
                          or bank.id::text = any(relation.row_ids)
                      )
                ) active_relations on true
                where bank.status <> 'deleted'
                  and (
                      bank.id::text = any(%s::text[])
                      or bank.legacy_mongo_id = any(%s::text[])
                  )
                order by array_position(
                    %s::text[],
                    coalesce(bank.legacy_mongo_id, bank.id::text)
                )
                """,
                (row_ids, row_ids, row_ids),
            )
            events = transaction.fetch_all(
                """
                select event_type, actor_id, occurred_at, payload
                from app.bank_flow_rule_batch_events
                where batch_id = %s
                order by occurred_at, id
                """,
                (normalized_batch_id,),
            )
        return {
            "batch": batch,
            "rows": [self._bank_row_payload(row) for row in bank_rows],
            "events": [self._event_payload(row) for row in events],
            "tag_policy": tag_policy,
            "tag_dictionary": tag_sources["tag_dictionary"],
        }

    def read_batch(self, batch_id: str) -> dict[str, object] | None:
        detail = self.read_detail(batch_id)
        batch = detail.get("batch") if isinstance(detail, dict) else None
        return dict(batch) if isinstance(batch, dict) else None

    def read_submitted_batches(self) -> list[dict[str, object]]:
        with self._snapshot() as transaction:
            rows = transaction.fetch_all(
                """
                select
                    batch.*,
                    coalesce(batch.raw_payload->'normalized_payload', '{}'::jsonb) as payload,
                    exists (
                        select 1
                        from app.workbench_pair_relations relation
                        where relation.status = 'active'
                          and relation.case_id = coalesce(
                              nullif(batch.raw_payload->'normalized_payload'->>'relation_case_id', ''),
                              batch.batch_id
                          )
                    ) as has_active_relation
                from app.bank_flow_rule_batches batch
                where batch.status = 'submitted'
                order by batch.scope_month, batch.batch_id
                """
            )
        return [self._batch_payload(row) for row in rows]

    def affected_scope_keys_for_tag_codes(self, tag_codes: list[str]) -> list[str]:
        normalized_codes = list(dict.fromkeys(text(code) for code in tag_codes if text(code)))
        if not normalized_codes:
            return []
        rows = self._connection.fetch_all(
            """
            with categorized_scopes as (
                select coalesce(bank.txn_month, date_trunc('month', bank.txn_date)::date) as scope_month
                from app.bank_transactions bank
                where bank.status <> 'deleted'
            )
            select to_char(scope_month, 'YYYY-MM') as scope_key
            from categorized_scopes
            where scope_month is not null
            group by scope_month
            order by scope_month
            """
        )
        return [scope_key for row in rows if (scope_key := text(row.get("scope_key")))]

    @contextmanager
    def _snapshot(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction

    @staticmethod
    def _tag_policy(transaction: Any) -> dict[str, object]:
        return BankFlowRuleBatchCanonicalQueryRepository._tag_sources(transaction)[
            "tag_policy"
        ]

    @staticmethod
    def _tag_sources(transaction: Any) -> dict[str, dict[str, object]]:
        row = transaction.fetch_one(
            """
            select settings_payload
            from app.app_settings
            where settings_key = 'app_settings'
            limit 1
            """
        )
        settings = row.get("settings_payload") if isinstance(row, dict) else None
        settings = settings if isinstance(settings, dict) else {}
        rules = settings.get("bank_flow_rule_batch_tag_rules")
        tags = settings.get("bank_transaction_tags")
        tag_dictionary = tags if isinstance(tags, dict) else {}
        return {
            "tag_policy": AppSettingsService._public_bank_transaction_paired_policy(
                rules if isinstance(rules, dict) else {},
                bank_transaction_tags=tag_dictionary,
            ),
            "tag_dictionary": tag_dictionary,
        }

    @staticmethod
    def _eligible_codes(tag_policy: dict[str, object]) -> list[str]:
        requirements = tag_policy.get("requirements_by_tag_code")
        requirements = requirements if isinstance(requirements, dict) else {}
        return [
            text(tag.get("code"))
            for tag in list(tag_policy.get("active_tags") or [])
            if isinstance(tag, dict)
            and text(tag.get("code"))
            and isinstance(requirements.get(text(tag.get("code"))), dict)
            and requirements[text(tag.get("code"))].get("requires_oa") is False
            and requirements[text(tag.get("code"))].get("requires_invoice") is False
        ]

    @staticmethod
    def _filters_sql(filters: dict[str, object] | None) -> tuple[str, list[object]]:
        resolved = filters if isinstance(filters, dict) else {}
        where = ["true"]
        params: list[object] = []
        if value := text(resolved.get("month")):
            if (
                len(value) != 7
                or value[4] != "-"
                or not value[:4].isdigit()
                or not value[5:].isdigit()
                or not 1 <= int(value[5:]) <= 12
            ):
                raise ValueError("invalid_bank_flow_rule_batch_month")
            where.append("scope_month = %s::date")
            params.append(month_start(value))
        if value := text(resolved.get("type")):
            if value != "all":
                where.append("batch_type = %s")
                params.append(value)
        if value := text(resolved.get("status")):
            if value not in {"all", "draft", "submitted", "withdrawn"}:
                raise ValueError("invalid_bank_flow_rule_batch_status")
            if value != "all":
                where.append("presented_status = %s")
                params.append(value)
        if value := text(resolved.get("bucket")):
            if value not in {"all", "unsubmitted", "submitted", "withdrawn"}:
                raise ValueError("invalid_bank_flow_rule_batch_bucket")
            if value != "all":
                where.append("presented_status_bucket = %s")
                params.append(value)
        if value := text(resolved.get("account_key")):
            where.append("account_key = %s")
            params.append(value)
        return " and ".join(where), params

    @staticmethod
    def _batch_payload(row: dict[str, object]) -> dict[str, object]:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row_payload(row, "raw_payload")
        result = dict(payload) if isinstance(payload, dict) else {}
        raw_status = text(row.get("status") or result.get("status")) or "draft"
        has_active_relation = bool(row.get("has_active_relation"))
        presented_status = text(row.get("presented_status"))
        if not presented_status:
            presented_status = "submitted" if raw_status == "stale" and has_active_relation else raw_status
            if raw_status == "unsubmitted" and text(row.get("status_bucket")) == "unsubmitted":
                presented_status = "draft"
        status_bucket = text(row.get("presented_status_bucket"))
        if not status_bucket:
            status_bucket = {
                "draft": "unsubmitted",
                "submitted": "submitted",
                "withdrawn": "withdrawn",
            }.get(presented_status, text(row.get("status_bucket")))
        result.update(
            {
                "batch_id": text(row.get("batch_id") or result.get("batch_id")),
                "status": presented_status,
                "status_bucket": status_bucket,
                "version": int_value(row.get("version"), int_value(result.get("version"), 1)),
                "scope_month": BankFlowRuleBatchCanonicalQueryRepository._month_text(
                    row.get("scope_month") or result.get("scope_month")
                ),
                "account_key": text(row.get("account_key") or result.get("account_key")),
                "total_amount": BankFlowRuleBatchCanonicalQueryRepository._decimal_text(
                    row.get("total_amount") if row.get("total_amount") is not None else result.get("total_amount")
                ),
                "row_ids": text_list(row.get("bank_transaction_ids") or result.get("row_ids")),
                "submitted_by": text(row.get("submitted_by") or result.get("submitted_by")),
                "submitted_at": BankFlowRuleBatchCanonicalQueryRepository._timestamp_text(
                    row.get("submitted_at") or result.get("submitted_at")
                ),
                "withdrawn_by": text(row.get("withdrawn_by") or result.get("withdrawn_by")),
                "withdrawn_at": BankFlowRuleBatchCanonicalQueryRepository._timestamp_text(
                    row.get("withdrawn_at") or result.get("withdrawn_at")
                ),
                "can_submit": presented_status == "draft",
                "can_withdraw": presented_status == "submitted" and has_active_relation,
            }
        )
        if raw_status == "stale" and has_active_relation:
            result["relation_backed_status"] = "stale"
        return result

    @staticmethod
    def _bank_row_payload(row: dict[str, object]) -> dict[str, object]:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else row_payload(row, "raw_payload")
        result = dict(payload) if isinstance(payload, dict) else {}
        transaction_id = text(row.get("transaction_id"))
        amount = BankFlowRuleBatchCanonicalQueryRepository._decimal_text(row.get("amount"))
        direction = text(row.get("txn_direction")).lower()
        account_no = text(row.get("account_no")) or ""
        bank_name = text(
            result.get("bank_name")
            or result.get("imported_bank_name")
            or row.get("bank_name")
        )
        account_last4 = text(
            result.get("account_last4")
            or result.get("imported_bank_last4")
            or row.get("account_last4")
        )
        if not account_last4:
            digits = "".join(character for character in account_no if character.isdigit())
            account_last4 = digits[-4:] if digits else ""
        result.update(
            {
                "id": transaction_id,
                "transaction_id": transaction_id,
                "account_no": account_no,
                "account_key": text(result.get("account_key") or row.get("account_key"))
                or f"{bank_name}:{account_last4}".strip(":"),
                "bank_name": bank_name,
                "account_last4": account_last4,
                "counterparty_name": text(
                    row.get("normalized_counterparty_name")
                    or row.get("counterparty_name_raw")
                ),
                "amount": amount,
                "direction": "income" if direction in {"inflow", "income", "收", "进"} else "expense",
                "direction_label": "收" if direction in {"inflow", "income", "收", "进"} else "支",
                "trade_time": BankFlowRuleBatchCanonicalQueryRepository._timestamp_text(
                    row.get("trade_time") or row.get("pay_receive_time") or row.get("txn_date")
                ),
                "summary": text(row.get("summary")),
                "purpose": text(
                    result.get("purpose")
                    or result.get("usage")
                    or result.get("use")
                    or row.get("purpose")
                ),
                "remark": text(row.get("remark")),
                "category_code": text(row.get("category_code")),
                "category_source": text(row.get("category_source")),
                "category_resolution_authority": text(
                    row.get("category_resolution_authority")
                ),
                "relation_status": "linked" if text_list(row.get("relation_case_ids")) else "unlinked",
                "relation_case_ids": text_list(row.get("relation_case_ids")),
                "linked_oa_count": int_value(row.get("linked_oa_count"), 0),
                "linked_invoice_count": int_value(row.get("linked_invoice_count"), 0),
            }
        )
        return result

    @staticmethod
    def _event_payload(row: dict[str, object]) -> dict[str, object]:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        return {
            "event_type": text(row.get("event_type")),
            "actor_id": text(row.get("actor_id")),
            "occurred_at": BankFlowRuleBatchCanonicalQueryRepository._timestamp_text(row.get("occurred_at")),
            "payload": dict(payload),
        }

    @staticmethod
    def _month_text(value: object) -> str:
        if isinstance(value, (date, datetime)):
            return value.strftime("%Y-%m")
        return text(value)[:7]

    @staticmethod
    def _timestamp_text(value: object) -> str:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return text(value)

    @staticmethod
    def _decimal_text(value: object) -> str:
        try:
            return f"{Decimal(str(value or 0)):.2f}"
        except (ValueError, ArithmeticError):
            return "0.00"
