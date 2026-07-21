from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.pending_invoice_rules import (
    pending_invoice_effective_category_payload,
    pending_invoice_group_for_category,
    pending_invoice_tag_group_sets,
)
from fin_ops_platform.services.pending_invoice_relation_identity import (
    infer_pending_invoice_relation_row_type,
    is_valid_pending_invoice_oa_row_id,
    sanitize_pending_invoice_oa_summaries,
)
from fin_ops_platform.services.pending_invoice_status import (
    pending_invoice_available_actions,
    pending_invoice_status_matches_filter,
    pending_invoice_status_payload,
)
from fin_ops_platform.services.pending_invoice_read_model_repository import PendingInvoiceReadModelRepositoryPort
from fin_ops_platform.services.search_read_model_repository import SearchReadModelRepositoryPort
from fin_ops_platform.services.invoice_lifecycle_policy import INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload, text, text_list
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
EXPENSE_PENDING_INVOICE_FILTERS = {"all", "requires_invoice", "bank_statement_as_invoice", "no_invoice_required"}
INCOME_PENDING_INVOICE_FILTERS = {"all", "requires_invoice", "no_invoice_required", "cash_income"}
PENDING_INVOICE_FILTERS = EXPENSE_PENDING_INVOICE_FILTERS | INCOME_PENDING_INVOICE_FILTERS


class SearchPendingSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: Any | None = None,
        pending_invoice_read_model_repository: Any | None = None,
        bank_transaction_tag_read_facade: Any | None = None,
        workbench_relation_read_facade: Any | None = None,
        relation_rows_from_source: bool = False,
    ) -> None:
        self._connection = connection
        broad_read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._search_read_model_repository = SearchReadModelRepositoryPort(broad_read_model_repository)
        self._read_model_repository = broad_read_model_repository
        self._pending_invoice_read_model_repository = (
            pending_invoice_read_model_repository
            or PendingInvoiceReadModelRepositoryPort(self._read_model_repository)
        )
        self._bank_transaction_tag_read_facade = bank_transaction_tag_read_facade
        self._workbench_relation_read_facade = workbench_relation_read_facade
        self._relation_rows_from_source = bool(relation_rows_from_source)
        self._pending_invoice_bank_tag_source_versions: dict[str, object] = {}
        self._pending_invoice_relation_source_versions: dict[str, object] = {}

    def list_search_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope = str(scope_key or "").strip()
        if normalized_scope != "all":
            return [normalized_scope] if MONTH_RE.match(normalized_scope) else []
        rows = self._connection.fetch_all(
            """
            select distinct to_char(scope_month, 'YYYY-MM') as scope_key
            from read_model.workbench_rows
            where scope_month is not null
            order by scope_key desc
            """
        )
        return [str(row.get("scope_key")) for row in rows if MONTH_RE.match(str(row.get("scope_key") or ""))]

    def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope = str(scope_key or "").strip()
        if not MONTH_RE.match(normalized_scope):
            raise ValueError("search SQL projection scope_key must be a month shard YYYY-MM.")
        source_versions = self._search_source_versions()
        unchanged = self._unchanged_search_scope_result(
            scope_key=normalized_scope,
            source_versions=source_versions,
        )
        if unchanged is not None:
            return unchanged
        rows = self._search_rows_for_month(normalized_scope)
        source_versions = self._search_source_versions()
        self._search_read_model_repository.save_search_index_rows(
            scope_key=normalized_scope,
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": normalized_scope, "row_count": len(rows), "source_versions": source_versions}

    def _unchanged_search_scope_result(
        self,
        *,
        scope_key: str,
        source_versions: dict[str, object],
    ) -> dict[str, object] | None:
        scope_summary_loader = getattr(self._search_read_model_repository, "search_index_scope_summary", None)
        if not callable(scope_summary_loader):
            return None
        scope_summary = scope_summary_loader(month=scope_key)
        if not isinstance(scope_summary, dict) or str(scope_summary.get("read_model_status") or "") != "fresh":
            return None
        existing_source_versions = scope_summary.get("source_versions")
        if not isinstance(existing_source_versions, dict) or existing_source_versions != source_versions:
            return None
        return {
            "scope_key": scope_key,
            "row_count": max(int(scope_summary.get("row_count") or 0), 0),
            "source_versions": source_versions,
            "skipped": True,
            "skip_reason": "source_versions_unchanged",
        }

    def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_direction, normalized_filter, month = _parse_pending_invoice_scope_key(scope_key)
        if normalized_direction not in {"expense", "income"}:
            raise ValueError("pending invoice direction must be expense or income.")
        if normalized_filter not in _pending_invoice_filters_for_direction(normalized_direction):
            raise ValueError("pending invoice filter must be all or a supported filter group.")
        if month is None:
            raise ValueError("pending invoice SQL projection scope_key must include a month shard YYYY-MM.")
        statistics_members: dict[str, dict[str, object]] = {}
        rows = self._pending_invoice_rows(
            direction=normalized_direction,
            filter_name=normalized_filter,
            month=month,
            statistics_members=statistics_members,
        )
        source_versions = self._pending_invoice_source_versions()
        self._pending_invoice_read_model_repository.save_pending_invoice_rows(
            scope_key=f"{normalized_direction}:{normalized_filter}:{month}",
            rows=rows,
            source_versions=source_versions,
            statistics_metadata={
                "statistics": _pending_invoice_statistics_from_members(statistics_members),
            },
        )
        return {"scope_key": f"{normalized_direction}:{normalized_filter}:{month}", "row_count": len(rows), "source_versions": source_versions}

    def mark_pending_invoice_scope_empty(self, scope_key: str) -> dict[str, object]:
        normalized_direction, normalized_filter, _month = _parse_pending_invoice_scope_key(scope_key)
        if normalized_direction not in {"expense", "income"}:
            raise ValueError("pending invoice direction must be expense or income.")
        if normalized_filter not in _pending_invoice_filters_for_direction(normalized_direction):
            raise ValueError("pending invoice filter must be all or a supported filter group.")
        mark_scope = getattr(self._pending_invoice_read_model_repository, "mark_pending_invoice_scope", None)
        if not callable(mark_scope):
            return {"scope_key": f"{normalized_direction}:{normalized_filter}", "row_count": 0}
        normalized_scope_key = str(scope_key or "").strip() or f"{normalized_direction}:{normalized_filter}"
        mark_scope(
            scope_key=normalized_scope_key,
            row_count=0,
            source_versions=self._pending_invoice_source_versions(),
            statistics_metadata={"statistics": _pending_invoice_statistics_from_members({})},
        )
        return {"scope_key": normalized_scope_key, "row_count": 0}

    def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
        normalized_direction, normalized_filter, month = _parse_pending_invoice_scope_key(scope_key)
        if normalized_direction not in {"expense", "income"}:
            return []
        if normalized_filter not in _pending_invoice_filters_for_direction(normalized_direction):
            return []
        if month is not None:
            return [f"{normalized_direction}:{normalized_filter}:{month}"]
        txn_direction = "outflow" if normalized_direction == "expense" else "inflow"
        rows = self._connection.fetch_all(
            """
            select distinct covered.scope_key
            from (
                select to_char(txn_month, 'YYYY-MM') as scope_key
                from app.bank_transactions
                where txn_month is not null
                  and txn_direction = %s
                  and status <> 'deleted'
                union
                select split_part(scope_key, ':', 3) as scope_key
                from read_model.pending_invoice_scopes
                where direction = %s
                  and filter_group = %s
                  and scope_key ~ '^(expense|income):[^:]+:[0-9]{4}-[0-9]{2}$'
            ) covered
            where covered.scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by covered.scope_key desc
            """,
            (txn_direction, normalized_direction, normalized_filter),
        )
        return [
            f"{normalized_direction}:{normalized_filter}:{row['scope_key']}"
            for row in rows
            if MONTH_RE.match(str(row.get("scope_key") or ""))
        ]

    def _search_rows_for_month(self, month: str) -> list[dict[str, object]]:
        rows = self._connection.fetch_all(
            """
            with ranked_rows as (
                select
                    generation_id,
                    row_id,
                    scope_key,
                    source_kind,
                    status,
                    scope_month,
                    project_name,
                    counterparty_name,
                    amount,
                    generated_at,
                    payload,
                    raw_payload,
                    row_number() over (
                        partition by row_id
                        order by generated_at desc nulls last, source_kind, status
                    ) as row_rank
                from read_model.workbench_rows
                where scope_month = %s::date
                  and (scope_key = %s or scope_key is null)
                  and row_id is not null
            )
            select ranked_rows.row_id, ranked_rows.source_kind, ranked_rows.status, ranked_rows.scope_month,
                   ranked_rows.project_name, ranked_rows.counterparty_name, ranked_rows.amount,
                   ranked_rows.generated_at, ranked_rows.payload, ranked_rows.raw_payload,
                   group_row.zone as group_zone, group_row.group_id
            from ranked_rows
            left join lateral (
                select zone, group_id
                from read_model.workbench_group_rows group_rows
                where group_rows.generation_id = ranked_rows.generation_id
                  and group_rows.scope_key = ranked_rows.scope_key
                  and group_rows.row_id = ranked_rows.row_id
                order by case when zone = 'paired' then 0 else 1 end, zone, group_id, row_index
                limit 1
            ) group_row on true
            where row_rank = 1
            order by ranked_rows.source_kind, ranked_rows.row_id
            """,
            (month_start(month), month),
        )
        result: list[dict[str, object]] = []
        for row in rows:
            payload = _payload_from_row(row)
            row_id = str(row.get("row_id") or payload.get("id") or payload.get("row_id") or "").strip()
            source_kind = str(row.get("source_kind") or payload.get("type") or payload.get("record_type") or "").strip()
            if not row_id or source_kind not in {"oa", "bank", "invoice"}:
                continue
            zone_hint = str(row.get("group_zone") or row.get("status") or payload.get("zone_hint") or "unpaired").strip() or "unpaired"
            group_id = text(row.get("group_id") or payload.get("group_id"))
            title = _search_title(source_kind, payload, row)
            primary_meta = _primary_meta(payload, row)
            secondary_meta = _secondary_meta(payload, row)
            searchable_text = _join_text(
                row_id,
                title,
                primary_meta,
                secondary_meta,
                row.get("project_name"),
                row.get("counterparty_name"),
                payload.get("invoice_no"),
                payload.get("digital_invoice_no"),
                payload.get("applicant"),
                payload.get("reason"),
                payload.get("remark"),
                payload.get("summary"),
                group_id,
            )
            result_payload = {
                "row_id": row_id,
                "record_type": source_kind,
                "month": month,
                "zone_hint": zone_hint,
                "matched_field": "全文",
                "title": title,
                "primary_meta": primary_meta,
                "secondary_meta": secondary_meta,
                "status_label": _status_label(zone_hint),
                "jump_target": {"month": month, "row_id": row_id, "record_type": source_kind, "zone_hint": zone_hint},
            }
            if group_id:
                result_payload["group_id"] = group_id
                result_payload["jump_target"]["group_id"] = group_id
            result.append(
                {
                    "row_id": row_id,
                    "source_kind": source_kind,
                    "status": zone_hint,
                    "title": title,
                    "subtitle": secondary_meta,
                    "searchable_text": searchable_text,
                    "project_name": row.get("project_name") or payload.get("project_name"),
                    "counterparty_name": row.get("counterparty_name") or payload.get("counterparty_name"),
                    "amount": row.get("amount") or payload.get("amount"),
                    "generated_at": row.get("generated_at"),
                    "payload": result_payload,
                }
            )
        return result

    def _pending_invoice_rows(
        self,
        *,
        direction: str,
        filter_name: str,
        month: str,
        statistics_members: dict[str, dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        txn_direction = "outflow" if direction == "expense" else "inflow"
        target_invoice_type = "input" if direction == "expense" else "output"
        tag_groups = self._pending_invoice_tag_groups(direction=direction)
        bank_tag_rows_by_id = self._bank_tag_rows_by_transaction_id(direction=direction, month=month)
        rows = self._connection.fetch_all(
            """
            select
                coalesce(t.legacy_mongo_id, t.id::text) as transaction_id,
                t.counterparty_name_raw,
                t.trade_time,
                t.txn_date,
                t.amount,
                t.balance,
                t.currency,
                t.summary,
                t.remark,
                t.bank_serial_no,
                t.account_name,
                t.account_no,
                coalesce(
                    t.raw_payload->'normalized_payload'->>'imported_bank_name',
                    t.raw_payload->'normalized_payload'->>'bank_name',
                    t.raw_payload->>'imported_bank_name',
                    t.raw_payload->>'bank_name',
                    ''
                ) as bank_name,
                coalesce(
                    t.raw_payload->'normalized_payload'->>'bank_short_name',
                    t.raw_payload->>'bank_short_name',
                    ''
                ) as bank_short_name,
                coalesce(
                    t.raw_payload->'normalized_payload'->>'counterparty_account_no',
                    t.raw_payload->>'counterparty_account_no',
                    ''
                ) as counterparty_account_no,
                coalesce(
                    t.raw_payload->'normalized_payload'->>'counterparty_bank_name',
                    t.raw_payload->>'counterparty_bank_name',
                    ''
                ) as counterparty_bank_name,
                t.txn_direction,
                t.txn_month,
                c.raw_payload as category_payload,
                '[]'::jsonb as invoices,
                '0' as paid_total,
                '' as oa_applicant,
                '' as oa_project_name,
                '[]'::jsonb as oa_summaries,
                iso.income_status_override,
                array[]::text[] as relation_case_ids
            from app.bank_transactions t
            left join lateral (
                select raw_payload
                from app.bank_transaction_categories c
                where c.status = 'active'
                  and (c.legacy_transaction_id = coalesce(t.legacy_mongo_id, t.id::text) or c.bank_transaction_id = t.id)
                order by c.updated_at desc
                limit 1
            ) c on true
            left join lateral (
                select override_payload as income_status_override
                from (
                    select command.updated_at, command.command_payload->'income_status_override' as override_payload
                    from app.pending_invoice_manual_invoice_commands command
                    where command.status = 'completed'
                      and command.command_payload->>'operation' = 'income_status_override'
                      and jsonb_typeof(command.command_payload->'income_status_override') = 'object'
                      and command.command_payload->'income_status_override'->>'transaction_id' = coalesce(t.legacy_mongo_id, t.id::text)
                    union all
                    select command.updated_at, batch_override.override_payload
                    from app.pending_invoice_manual_invoice_commands command
                    cross join lateral jsonb_array_elements(
                        case
                            when jsonb_typeof(command.command_payload->'income_status_overrides') = 'array'
                            then command.command_payload->'income_status_overrides'
                            else '[]'::jsonb
                        end
                    ) as batch_override(override_payload)
                    where command.status = 'completed'
                      and command.command_payload->>'operation' = 'income_status_override'
                      and batch_override.override_payload->>'transaction_id' = coalesce(t.legacy_mongo_id, t.id::text)
                ) override_rows
                order by updated_at desc
                limit 1
            ) iso on true
            where t.txn_direction = %s
              and t.status <> 'deleted'
              and t.txn_month = %s::date
            order by coalesce(t.trade_time, t.txn_date::timestamptz) desc, transaction_id
            """,
            (txn_direction, month_start(month)),
        )
        result: list[dict[str, object]] = []
        relation_rows_by_id = self._workbench_relation_rows_by_transaction_id(
            row_ids=[str(row.get("transaction_id") or "").strip() for row in rows],
            month=month,
        )
        emitted_relation_groups: set[str] = set()
        for row in rows:
            transaction_id = str(row.get("transaction_id") or "").strip()
            relation_context = relation_rows_by_id.get(transaction_id) or {}
            category = bank_tag_rows_by_id.get(transaction_id) or row_payload(row, "category_payload")
            category = category if isinstance(category, dict) else {}
            effective_category = pending_invoice_effective_category_payload(category)
            category_code = str(effective_category.get("category_code") or "").strip()
            filter_group = _filter_group_for_category(category_code, tag_groups, direction=direction) or "all"
            invoices = _relation_invoice_summaries(relation_context, target_invoice_type=target_invoice_type)
            if not invoices:
                invoices = row.get("invoices") if isinstance(row.get("invoices"), list) else []
            linked_invoices = [invoice for invoice in invoices if _distribution_item_is_linked(invoice)]
            paid_total = _relation_paid_total(relation_context) if relation_context else row.get("paid_total")
            payment_summary = _payment_summary_from_invoices(linked_invoices, paid_total=paid_total)
            can_create_invoice = direction == "expense" and not linked_invoices and filter_group != "no_invoice_required"
            relation_case_ids = _relation_case_ids(relation_context) or list(row.get("relation_case_ids") or [])
            relation_oa_summaries = _relation_oa_summaries(relation_context)
            oa_applicant = str(
                (relation_oa_summaries[0].get("applicant") if relation_oa_summaries else None)
                or row.get("oa_applicant")
                or ""
            ).strip()
            oa_project_name = str(
                (relation_oa_summaries[0].get("project_name") if relation_oa_summaries else None)
                or row.get("oa_project_name")
                or ""
            ).strip()
            oa_summaries, invalid_oa_summary_ids = sanitize_pending_invoice_oa_summaries(
                relation_oa_summaries or row.get("oa_summaries")
            )
            if not oa_summaries and not invalid_oa_summary_ids and (oa_applicant or oa_project_name):
                oa_summaries = [
                    {
                        "id": "",
                        "applicant": oa_applicant,
                        "project_name": oa_project_name,
                        "detail_available": False,
                    }
                ]
            status_payload = pending_invoice_status_payload(
                direction=direction,
                group=filter_group if filter_group != "all" else None,
                has_invoices=bool(linked_invoices),
                payment_summary=payment_summary,
                matched_rule=_matched_rule_payload(
                    group=filter_group if filter_group != "all" else None,
                    category_code=category_code,
                    category_label=effective_category.get("category_label"),
                    category=effective_category,
                ),
                status_override=row.get("income_status_override") if isinstance(row.get("income_status_override"), dict) else None,
            )
            if statistics_members is not None:
                status_code = str(status_payload.get("code") or "")
                statistics_members[transaction_id] = {
                    "transaction_id": transaction_id,
                    "direction": direction,
                    "linked_oa": any(
                        bool(text(summary.get("id"))) and _distribution_item_is_linked(summary)
                        for summary in oa_summaries
                        if isinstance(summary, dict)
                    ),
                    "linked_invoice": bool(linked_invoices),
                    "pending_invoice": status_code
                    in {"paid_pending_invoice", "paid_pending_future_invoice", "income_pending_invoice"},
                    "no_invoice_required": status_code
                    in {"no_invoice_required", "income_no_invoice_required"},
                    "cash_income": status_code == "cash_income",
                }
            if filter_name != "all" and not pending_invoice_status_matches_filter(
                direction=direction,
                filter_name=filter_name,
                status_code=str(status_payload.get("code") or ""),
            ):
                continue
            available_actions = pending_invoice_available_actions(status_payload, can_create_invoice=can_create_invoice)
            bank_transaction = {
                "id": transaction_id,
                "counterparty_name": row.get("counterparty_name_raw"),
                "counterparty_account_no": row.get("counterparty_account_no") or "",
                "counterparty_bank_name": row.get("counterparty_bank_name") or "",
                "trade_time": _date_text(row.get("trade_time") or row.get("txn_date")),
                "booked_date": _date_text(row.get("txn_date")),
                "trade_date": _date_text(row.get("txn_date") or row.get("trade_time"))[:10],
                "amount": str(row.get("amount") or ""),
                "debit_amount": str(row.get("amount") or "") if direction == "expense" else "0.00",
                "credit_amount": str(row.get("amount") or "") if direction == "income" else "0.00",
                "balance": str(row.get("balance") or ""),
                "currency": row.get("currency") or "CNY",
                "bank_name": row.get("bank_name") or "",
                "bank_short_name": row.get("bank_short_name") or row.get("bank_name") or "",
                "account_name": row.get("account_name") or "",
                "account_last4": str(row.get("account_no") or "")[-4:],
                "summary": row.get("summary") or "",
                "remark": row.get("remark") or "",
                "statement_serial_no": row.get("bank_serial_no") or "",
                "enterprise_serial_no": "",
                "voucher_type": "",
                "voucher_no": "",
                "effective_tag_code": category_code or None,
                "effective_tag_label": effective_category.get("category_label"),
                "effective_tag_primary_label": effective_category.get("category_primary_label"),
                "effective_tag_sub_label": effective_category.get("category_sub_label"),
                "effective_tag_label_path": list(effective_category.get("category_label_path") or []),
            }
            bank_transactions = _bank_transactions_payload(
                relation_context,
                fallback=bank_transaction,
                paid_total=str(payment_summary.get("paid_total") or "0.00"),
            )
            input_invoices = {
                "primary": invoices[0] if invoices else None,
                "relation_count": len(invoices),
                "linked_relation_count": len(linked_invoices),
                "has_multiple": len(invoices) > 1,
                "summaries": invoices,
                "payment_summary": payment_summary,
            }
            oa_payload = {
                "primary": oa_summaries[0] if oa_summaries else None,
                "relation_count": len(oa_summaries),
                "has_multiple": len(oa_summaries) > 1,
                "detail_available": any(bool(summary.get("detail_available")) for summary in oa_summaries),
                "summaries": oa_summaries,
            }
            if invalid_oa_summary_ids:
                oa_payload["invalid_oa_summary_ids"] = invalid_oa_summary_ids
            payload = {
                "id": transaction_id,
                "bank_transaction": bank_transaction,
                "bank_transactions": bank_transactions,
                "invoice_acquisition_status": status_payload,
                "input_invoices": input_invoices,
                "oa": oa_payload,
                "invoices": invoices,
                "oa_applicant": oa_applicant or "—",
                "can_create_invoice": can_create_invoice,
                "available_actions": available_actions,
                "relation_case_ids": relation_case_ids,
                "filter_group": filter_group,
            }
            relation_group_key = _multi_bank_relation_group_key(payload)
            if relation_group_key and relation_group_key in emitted_relation_groups:
                continue
            searchable_text = _join_text(
                transaction_id,
                bank_transaction.get("counterparty_name"),
                bank_transaction.get("trade_time"),
                bank_transaction.get("amount"),
                bank_transaction.get("effective_tag_label"),
                payload.get("oa_applicant"),
            )
            result.append({"filter_group": filter_group, "searchable_text": searchable_text, "payload": payload})
            if relation_group_key:
                emitted_relation_groups.add(relation_group_key)
        return result

    def _pending_invoice_tag_groups(self, *, direction: str) -> dict[str, set[str]]:
        row = self._connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s",
            ("app_settings",),
        )
        payload = row.get("settings_payload") if isinstance(row, dict) else {}
        return pending_invoice_tag_group_sets(payload if isinstance(payload, dict) else {}, direction=direction)

    def _search_source_versions(self) -> dict[str, object]:
        return {
            "search_index_schema_version": "2026-05-search-index-v1",
            "workbench_read_model_schema_version": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
            "bank_auto_tag_rules_version": _current_bank_auto_tag_rules_version(self._connection),
            "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
        }

    def _bank_tag_rows_by_transaction_id(self, *, direction: str, month: str) -> dict[str, dict[str, object]]:
        self._pending_invoice_bank_tag_source_versions = {}
        facade = self._bank_transaction_tag_read_facade
        if facade is None:
            return {}
        list_by_month = getattr(facade, "list_by_month", None)
        if not callable(list_by_month):
            return {}
        payload = list_by_month(
            month,
            direction=direction,
            require_fresh=True,
            reason="pending_invoice_sql_projection",
        )
        if not isinstance(payload, dict) or str(payload.get("status") or "") != "fresh":
            raise RuntimeError("bank_detail_read_model_not_fresh")
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        self._pending_invoice_bank_tag_source_versions = dict(source_versions)
        return {
            transaction_id: _pending_invoice_category_payload_from_bank_tag_row(row)
            for row in list(payload.get("rows") or [])
            if isinstance(row, dict) and (transaction_id := str(row.get("transaction_id") or "").strip())
        }

    def _workbench_relation_rows_by_transaction_id(self, *, row_ids: list[str], month: str) -> dict[str, dict[str, object]]:
        self._pending_invoice_relation_source_versions = {}
        if self._relation_rows_from_source:
            return self._workbench_relation_rows_by_transaction_id_from_source(row_ids=row_ids, month=month)
        facade = self._workbench_relation_read_facade
        if facade is None:
            return {}
        get_by_row_ids = getattr(facade, "get_by_row_ids", None)
        if not callable(get_by_row_ids):
            return {}
        transaction_ids = _dedupe_preserve_order(text(row_id) for row_id in row_ids)
        if not transaction_ids:
            return {}
        payload = get_by_row_ids(
            transaction_ids,
            require_fresh=True,
            reason="pending_invoice_sql_projection",
            month_hint=month,
            scope_keys_hint=[month],
        )
        if not isinstance(payload, dict) or str(payload.get("status") or "") != "fresh":
            raise RuntimeError("workbench_relation_read_model_not_fresh")
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        self._pending_invoice_relation_source_versions = dict(source_versions)
        return {
            row_id: row
            for row in list(payload.get("rows") or [])
            if isinstance(row, dict) and (row_id := str(row.get("row_id") or "").strip()) in transaction_ids
        }

    def _workbench_relation_rows_by_transaction_id_from_source(
        self,
        *,
        row_ids: list[str],
        month: str,
    ) -> dict[str, dict[str, object]]:
        transaction_ids = _dedupe_preserve_order(text(row_id) for row_id in row_ids)
        if not transaction_ids:
            return {}
        self._pending_invoice_relation_source_versions = self._workbench_relation_source_versions_from_source(
            month=month,
            row_ids=transaction_ids,
        )
        source_reader = getattr(self._read_model_repository, "list_active_workbench_relation_source_rows", None)
        rows = (
            source_reader(row_ids=transaction_ids, include_member_summaries=True)
            if callable(source_reader)
            else []
        )
        return _source_relation_contexts_by_transaction_id(rows, transaction_ids)

    def _workbench_relation_source_versions_from_source(self, *, month: str, row_ids: list[str]) -> dict[str, object]:
        summary_reader = getattr(self._read_model_repository, "workbench_relation_source_summary_from_source", None)
        if not callable(summary_reader):
            return {}
        return dict(summary_reader(scope_key=month, row_ids=text_list(row_ids), include_row_ids=True))

    def _pending_invoice_source_versions(self) -> dict[str, object]:
        settings = _settings_payload(self._connection)
        pending_groups = settings.get("pending_invoice_tag_groups")
        pending_output_groups = settings.get("pending_output_invoice_tag_groups")
        bank_tags = settings.get("bank_transaction_tags")
        return {
            "pending_invoice_read_model_schema_version": "2026-06-pending-invoice-oa-identity-v2",
            "invoice_lifecycle_policy_schema_version": INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION,
            "pending_invoice_tag_groups_version": pending_groups.get("version") if isinstance(pending_groups, dict) else 1,
            "pending_output_invoice_tag_groups_version": pending_output_groups.get("version") if isinstance(pending_output_groups, dict) else 1,
            "bank_auto_tag_rules_version": bank_tags.get("version") if isinstance(bank_tags, dict) else 1,
            "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
            "bank_detail_source_versions": dict(self._pending_invoice_bank_tag_source_versions),
            "workbench_relation_source_versions": dict(self._pending_invoice_relation_source_versions),
        }


def _parse_pending_invoice_scope_key(scope_key: str) -> tuple[str, str, str | None]:
    parts = [part.strip() for part in str(scope_key or "").split(":")]
    direction = parts[0] if parts and parts[0] else "expense"
    filter_name = parts[1] if len(parts) > 1 and parts[1] else "all"
    month = parts[2] if len(parts) > 2 and parts[2] else ""
    normalized_month = month[:7] if MONTH_RE.match(month[:7]) else None
    return direction, filter_name, normalized_month


def _source_relation_contexts_by_transaction_id(
    rows: list[dict[str, object]],
    transaction_ids: list[str],
) -> dict[str, dict[str, object]]:
    transaction_id_set = set(transaction_ids)
    contexts: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        case_id = text(row.get("case_id"))
        row_ids = text_list(row.get("row_ids"))
        row_types = text_list(row.get("row_types"))
        bank_ids = [row_id for row_id in row_ids if row_id in transaction_id_set]
        if not bank_ids:
            continue
        relation_status = _source_relation_status(row)
        source_summaries = row.get("source_summaries") if isinstance(row.get("source_summaries"), dict) else {}
        linked_oa = _source_relation_oa_summaries(
            row_ids,
            row_types,
            case_id=case_id,
            relation_status=relation_status,
            source_summaries=source_summaries,
        )
        linked_bank_transactions: list[dict[str, object]] = []
        for index, row_id in enumerate(row_ids):
            row_type = _source_relation_row_type(row_ids, row_types, index)
            if row_type != "bank":
                continue
            source_summary = source_summaries.get(row_id)
            source_summary = source_summary if isinstance(source_summary, dict) else {}
            linked_bank_transactions.append(
                {
                    "id": row_id,
                    "amount": text(source_summary.get("amount")),
                    "counterparty_name": text(source_summary.get("counterparty_name")),
                    "trade_time": text(source_summary.get("trade_time")),
                    "summary": text(source_summary.get("summary")),
                    "remark": text(source_summary.get("remark")),
                    "statement_serial_no": text(source_summary.get("statement_serial_no")),
                    "account_name": text(source_summary.get("account_name")),
                    "account_last4": text(source_summary.get("account_last4")),
                    "relation_case_id": case_id,
                    "relation_status": relation_status,
                }
            )
        linked_input_invoices, linked_output_invoices = _source_relation_invoice_summaries(
            row_ids,
            row_types,
            case_id=case_id,
            relation_status=relation_status,
            source_summaries=source_summaries,
        )
        for bank_id in bank_ids:
            context = contexts.setdefault(
                bank_id,
                {
                    "row_id": bank_id,
                    "row_type": "bank_transaction",
                    "relation_status": relation_status,
                    "group_ids": [],
                    "linked_oa": [],
                    "linked_bank_transactions": [],
                    "linked_input_invoices": [],
                    "linked_output_invoices": [],
                },
            )
            _append_unique_text(context["group_ids"], case_id)
            _extend_unique_dicts(context["linked_oa"], linked_oa, key="id")
            _extend_unique_dicts(context["linked_bank_transactions"], linked_bank_transactions, key="id")
            _extend_unique_dicts(context["linked_input_invoices"], linked_input_invoices, key="id")
            _extend_unique_dicts(context["linked_output_invoices"], linked_output_invoices, key="id")
    return contexts


def _source_relation_oa_summaries(
    row_ids: list[str],
    row_types: list[str],
    *,
    case_id: str | None,
    relation_status: str,
    source_summaries: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    source_summaries = source_summaries or {}
    for index, row_id in enumerate(row_ids):
        row_type = _source_relation_row_type(row_ids, row_types, index)
        if row_type != "oa" or not is_valid_pending_invoice_oa_row_id(row_id):
            continue
        source_summary = source_summaries.get(row_id)
        source_summary = source_summary if isinstance(source_summary, dict) else {}
        summaries.append(
            {
                "id": row_id,
                "applicant": text(source_summary.get("applicant")),
                "application_type": text(source_summary.get("application_type") or source_summary.get("form_type")),
                "project_name": text(source_summary.get("project_name")),
                "status": text(source_summary.get("status")),
                "form_no": text(source_summary.get("form_no") or source_summary.get("form_id")),
                "amount": text(source_summary.get("amount")),
                "detail_available": bool(source_summary.get("detail_available", False)),
                "relation_case_id": case_id,
                "relation_status": relation_status,
                "relation_source": "workbench_pair_relations",
            }
        )
    return summaries


def _source_relation_invoice_summaries(
    row_ids: list[str],
    row_types: list[str],
    *,
    case_id: str | None,
    relation_status: str,
    source_summaries: dict[str, object] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    input_invoices: list[dict[str, object]] = []
    output_invoices: list[dict[str, object]] = []
    source_summaries = source_summaries or {}
    for index, row_id in enumerate(row_ids):
        row_type = _source_relation_row_type(row_ids, row_types, index)
        if row_type != "invoice":
            continue
        source_summary = source_summaries.get(row_id)
        source_summary = source_summary if isinstance(source_summary, dict) else {}
        invoice_type = text(source_summary.get("invoice_type")) or (
            "output" if _source_invoice_row_id_is_output(row_id) else "input"
        )
        if invoice_type not in {"input", "output"}:
            invoice_type = "input"
        summary = {
            "id": row_id,
            "invoice_no": text(source_summary.get("invoice_no")),
            "digital_invoice_no": text(source_summary.get("digital_invoice_no")),
            "invoice_code": text(source_summary.get("invoice_code")),
            "issue_date": text(source_summary.get("issue_date") or source_summary.get("invoice_date")),
            "total_with_tax": text(source_summary.get("total_with_tax") or source_summary.get("amount")),
            "seller_name": text(source_summary.get("seller_name")),
            "seller_tax_no": text(source_summary.get("seller_tax_no")),
            "buyer_name": text(source_summary.get("buyer_name")),
            "buyer_tax_no": text(source_summary.get("buyer_tax_no")),
            "invoice_type": invoice_type,
            "source_kind": text(source_summary.get("source_kind")),
            "relation_case_id": case_id,
            "relation_status": relation_status,
            "relation_source": "workbench_pair_relations",
        }
        if summary["invoice_type"] == "output":
            output_invoices.append(summary)
        else:
            input_invoices.append(summary)
    return input_invoices, output_invoices


def _source_relation_row_type(row_ids: list[str], row_types: list[str], index: int) -> str:
    if index < len(row_types) and row_types[index]:
        row_type = row_types[index]
        if row_type == "bank_transaction":
            return "bank"
        return row_type
    return infer_pending_invoice_relation_row_type(row_ids[index] if index < len(row_ids) else "")


def _source_invoice_row_id_is_output(row_id: str) -> bool:
    normalized = str(row_id or "").strip().lower()
    return normalized.startswith("output") or "output_invoice" in normalized or "销项" in normalized


def _source_relation_status(row: dict[str, object]) -> str:
    raw_status = text(row.get("relation_status") or row.get("status"))
    if raw_status in {None, "", "active"}:
        return "linked"
    return raw_status


def _append_unique_text(target: object, value: str | None) -> None:
    if not isinstance(target, list):
        return
    normalized = text(value)
    if normalized and normalized not in target:
        target.append(normalized)


def _extend_unique_dicts(target: object, values: list[dict[str, object]], *, key: str) -> None:
    if not isinstance(target, list):
        return
    seen = {
        text(item.get(key))
        for item in target
        if isinstance(item, dict) and text(item.get(key))
    }
    for value in values:
        identity = text(value.get(key))
        if not identity or identity in seen:
            continue
        seen.add(identity)
        target.append(dict(value))


def _relation_invoice_summaries(relation_context: dict[str, object], *, target_invoice_type: str) -> list[dict[str, object]]:
    if not isinstance(relation_context, dict):
        return []
    key = "linked_input_invoices" if target_invoice_type == "input" else "linked_output_invoices"
    summaries: list[dict[str, object]] = []
    for invoice in list(relation_context.get(key) or []):
        if not isinstance(invoice, dict):
            continue
        invoice_id = text(invoice.get("id") or invoice.get("invoice_id") or invoice.get("row_id"))
        if not invoice_id:
            continue
        seller_name = text(invoice.get("seller_name"))
        buyer_name = text(invoice.get("buyer_name"))
        summaries.append(
            {
                "id": invoice_id,
                "invoice_no": text(invoice.get("invoice_no")),
                "digital_invoice_no": text(invoice.get("digital_invoice_no")),
                "issue_date": text(invoice.get("issue_date") or invoice.get("invoice_date")),
                "total_with_tax": text(invoice.get("total_with_tax") or invoice.get("amount")),
                "seller_name": seller_name,
                "seller_tax_no": text(invoice.get("seller_tax_no")),
                "buyer_name": buyer_name,
                "buyer_tax_no": text(invoice.get("buyer_tax_no")),
                "invoice_type": text(invoice.get("invoice_type")) or target_invoice_type,
                "source_kind": text(invoice.get("source_kind")),
                "counterparty_display_name": seller_name if target_invoice_type == "input" else buyer_name,
                "relation_case_id": text(invoice.get("relation_case_id")),
                "relation_status": _distribution_item_relation_status(invoice),
                "relation_source": text(invoice.get("relation_source") or invoice.get("relationSource")),
            }
        )
    return summaries


def _relation_oa_summaries(relation_context: dict[str, object]) -> list[dict[str, object]]:
    if not isinstance(relation_context, dict):
        return []
    summaries: list[dict[str, object]] = []
    for oa in list(relation_context.get("linked_oa") or []):
        if not isinstance(oa, dict):
            continue
        oa_id = text(oa.get("id") or oa.get("oa_id") or oa.get("row_id"))
        if not oa_id:
            continue
        summaries.append(
            {
                "id": oa_id,
                "applicant": text(oa.get("applicant")),
                "application_type": text(oa.get("application_type") or oa.get("form_type")),
                "project_name": text(oa.get("project_name")),
                "status": text(oa.get("status")),
                "form_no": text(oa.get("form_no") or oa.get("form_id")),
                "detail_available": bool(oa.get("detail_available", True)),
                "relation_case_id": text(oa.get("relation_case_id")),
                "relation_status": _distribution_item_relation_status(oa),
                "relation_source": text(oa.get("relation_source") or oa.get("relationSource")),
            }
        )
    return summaries


def _relation_case_ids(relation_context: dict[str, object]) -> list[str]:
    if not isinstance(relation_context, dict):
        return []
    case_ids = _dedupe_preserve_order(text(value) for value in list(relation_context.get("group_ids") or []))
    for oa in list(relation_context.get("linked_oa") or []):
        if isinstance(oa, dict):
            case_ids.extend(value for value in [text(oa.get("relation_case_id"))] if value and value not in case_ids)
    return case_ids


def _relation_paid_total(relation_context: dict[str, object]) -> str:
    if not isinstance(relation_context, dict):
        return "0.00"
    total = sum(
        (
            _decimal_from_text(bank.get("amount"))
            for bank in list(relation_context.get("linked_bank_transactions") or [])
            if isinstance(bank, dict) and _distribution_item_is_linked(bank)
        ),
        start=Decimal("0.00"),
    )
    return _decimal_to_str(total)


def _bank_transactions_payload(
    relation_context: dict[str, object],
    *,
    fallback: dict[str, object],
    paid_total: str,
) -> dict[str, object]:
    summaries: list[dict[str, object]] = []
    seen: set[str] = set()
    linked_count = 0
    if isinstance(relation_context, dict):
        for bank in list(relation_context.get("linked_bank_transactions") or []):
            if not isinstance(bank, dict):
                continue
            transaction_id = text(bank.get("id") or bank.get("transaction_id") or bank.get("row_id"))
            if not transaction_id or transaction_id in seen:
                continue
            seen.add(transaction_id)
            if _distribution_item_is_linked(bank):
                linked_count += 1
            amount = text(bank.get("amount"))
            summaries.append(
                {
                    "id": transaction_id,
                    "trade_time": text(bank.get("trade_time")),
                    "booked_date": text(bank.get("booked_date")),
                    "counterparty_name": text(bank.get("counterparty_name")),
                    "amount": amount,
                    "debit_amount": text(bank.get("debit_amount")) or amount,
                    "credit_amount": text(bank.get("credit_amount")),
                    "bank_name": text(bank.get("bank_name")),
                    "bank_short_name": text(bank.get("bank_short_name") or bank.get("bank_name")),
                    "account_last4": text(bank.get("account_last4")),
                    "summary": text(bank.get("summary")),
                    "remark": text(bank.get("remark")),
                    "relation_case_id": text(bank.get("relation_case_id")),
                    "relation_status": _distribution_item_relation_status(bank),
                    "relation_source": text(bank.get("relation_source") or bank.get("relationSource")),
                }
            )
    if not summaries:
        summaries = [dict(fallback)]
        linked_count = 1
    return {
        "primary": summaries[0] if len(summaries) == 1 else None,
        "relation_count": len(summaries),
        "linked_relation_count": linked_count,
        "has_multiple": len(summaries) > 1,
        "detail_mode": "list" if len(summaries) > 1 else "single",
        "summaries": summaries,
        "payment_summary": {"paid_total": paid_total},
    }


def _multi_bank_relation_group_key(payload: dict[str, object]) -> str | None:
    bank_transactions = payload.get("bank_transactions") if isinstance(payload.get("bank_transactions"), dict) else {}
    summaries = list(bank_transactions.get("summaries") or []) if isinstance(bank_transactions, dict) else []
    if len(summaries) <= 1:
        return None
    for case_id in list(payload.get("relation_case_ids") or []):
        normalized = text(case_id)
        if normalized:
            return normalized
    return None


def _distribution_item_relation_status(item: dict[str, object] | None) -> str:
    if not isinstance(item, dict):
        return "linked"
    status = text(item.get("relation_status") or item.get("relationStatus"))
    return status or "linked"


def _distribution_item_is_linked(item: dict[str, object] | None) -> bool:
    return _distribution_item_relation_status(item) == "linked"


def _dedupe_preserve_order(values: object) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _pending_invoice_statistics_from_members(
    members: dict[str, dict[str, object]],
) -> dict[str, int]:
    values = list(members.values())
    return {
        "bank_transaction_count": len(values),
        "expense_transaction_count": sum(item.get("direction") == "expense" for item in values),
        "income_transaction_count": sum(item.get("direction") == "income" for item in values),
        "found_invoice_transaction_count": sum(bool(item.get("linked_invoice")) for item in values),
        "pending_invoice_transaction_count": sum(bool(item.get("pending_invoice")) for item in values),
        "no_invoice_required_transaction_count": sum(bool(item.get("no_invoice_required")) for item in values),
        "cash_income_transaction_count": sum(bool(item.get("cash_income")) for item in values),
        "linked_oa_transaction_count": sum(bool(item.get("linked_oa")) for item in values),
        "linked_input_invoice_transaction_count": sum(
            item.get("direction") == "expense" and bool(item.get("linked_invoice")) for item in values
        ),
        "linked_output_invoice_transaction_count": sum(
            item.get("direction") == "income" and bool(item.get("linked_invoice")) for item in values
        ),
    }


def _pending_invoice_filters_for_direction(direction: str) -> set[str]:
    return INCOME_PENDING_INVOICE_FILTERS if direction == "income" else EXPENSE_PENDING_INVOICE_FILTERS


def _settings_payload(connection: Any) -> dict[str, Any]:
    row = connection.fetch_one(
        "select settings_payload from app.app_settings where settings_key = %s",
        ("app_settings",),
    )
    payload = row.get("settings_payload") if isinstance(row, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _current_bank_auto_tag_rules_version(connection: Any) -> int:
    settings = _settings_payload(connection)
    rules_payload = settings.get("bank_transaction_tags")
    if not isinstance(rules_payload, dict):
        return 1
    try:
        return int(rules_payload.get("version") or 1)
    except (TypeError, ValueError):
        return 1


def _payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row_payload(row, "payload", "raw_payload")
    return payload if isinstance(payload, dict) else {}


def _search_title(source_kind: str, payload: dict[str, Any], row: dict[str, Any]) -> str:
    if source_kind == "oa":
        return str(payload.get("project_name") or payload.get("reason") or payload.get("applicant") or row.get("row_id") or "")
    if source_kind == "invoice":
        return str(payload.get("seller_name") or payload.get("buyer_name") or row.get("counterparty_name") or row.get("row_id") or "")
    return str(row.get("counterparty_name") or payload.get("counterparty_name") or row.get("row_id") or "")


def _primary_meta(payload: dict[str, Any], row: dict[str, Any]) -> str:
    return _join_text(
        payload.get("date"),
        payload.get("trade_time"),
        payload.get("invoice_date"),
        row.get("amount") or payload.get("amount"),
    )


def _secondary_meta(payload: dict[str, Any], row: dict[str, Any]) -> str:
    return _join_text(row.get("project_name") or payload.get("project_name"), row.get("counterparty_name") or payload.get("counterparty_name"))


def _join_text(*parts: object) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _status_label(status: str) -> str:
    return {
        "paired": "已配对",
        "unpaired": "未配对",
        "ignored": "已忽略",
        "processed_exception": "已处理异常",
    }.get(status, status)


def _filter_group_for_category(category_code: str, tag_groups: dict[str, set[str]], *, direction: str) -> str | None:
    return pending_invoice_group_for_category(category_code, tag_groups, direction=direction)


def _pending_invoice_category_payload_from_bank_tag_row(row: dict[str, Any]) -> dict[str, object]:
    label_path = list(row.get("effective_category_label_path") or [])
    category_code = str(row.get("effective_category_code") or "").strip()
    return {
        "category_code": category_code,
        "category_label": row.get("effective_category_label"),
        "category_primary_label": row.get("effective_category_primary_label"),
        "category_sub_label": row.get("effective_category_sub_label"),
        "category_third_label": row.get("effective_category_third_label"),
        "category_label_path": label_path,
        "category_path": label_path,
        "source": row.get("effective_category_source"),
        "category_source": row.get("effective_category_source"),
        "effective_category_code": category_code,
        "effective_category_label": row.get("effective_category_label"),
        "effective_category_primary_label": row.get("effective_category_primary_label"),
        "effective_category_sub_label": row.get("effective_category_sub_label"),
        "effective_category_third_label": row.get("effective_category_third_label"),
        "effective_category_label_path": label_path,
        "effective_category_path": label_path,
        "effective_category_source": row.get("effective_category_source"),
    }


def _matched_rule_payload(
    *,
    group: str | None,
    category_code: str,
    category_label: object,
    category: dict[str, object] | None = None,
) -> dict[str, object] | None:
    if not group:
        return None
    category_payload = category if isinstance(category, dict) else {}
    return {
        "group": group,
        "tag_code": category_code or None,
        "tag_label": category_label,
        "tag_primary_label": category_payload.get("category_primary_label"),
        "tag_sub_label": category_payload.get("category_sub_label"),
        "tag_label_path": list(category_payload.get("category_label_path") or []),
    }


def _payment_summary_from_invoices(invoices: list[object], *, paid_total: object) -> dict[str, object]:
    invoice_total = sum(
        (_invoice_total_from_payload(invoice) for invoice in invoices if isinstance(invoice, dict)),
        start=Decimal("0.00"),
    )
    normalized_paid_total = _decimal_from_text(paid_total)
    remaining = invoice_total - normalized_paid_total
    if remaining < Decimal("0.00"):
        remaining = Decimal("0.00")
    return {
        "invoice_total": _decimal_to_str(invoice_total),
        "paid_total": _decimal_to_str(normalized_paid_total),
        "remaining_amount": _decimal_to_str(remaining),
        "difference_amount": _decimal_to_str(invoice_total - normalized_paid_total),
        "payment_transaction_count": 0,
    }


def _invoice_total_from_payload(invoice: dict[str, object]) -> Decimal:
    return _decimal_from_text(invoice.get("total_with_tax") or invoice.get("amount"))


def _decimal_from_text(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _decimal_to_str(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _date_text(value: object) -> str:
    if isinstance(value, (date,)):
        return value.isoformat()
    return str(value or "")[:19]
