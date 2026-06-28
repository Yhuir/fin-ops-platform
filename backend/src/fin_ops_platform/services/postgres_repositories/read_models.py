from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from typing import Any
from urllib.parse import unquote

from fin_ops_platform.services.bank_transaction_category_service import BANK_TRANSACTION_CATEGORY_COUNT_KEYS
from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    int_value,
    iter_mapping,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    serialize_value,
    text,
    text_list,
    without_keys,
)
from fin_ops_platform.services.workbench_candidate_match_service import CANDIDATE_MATCH_SCHEMA_VERSION

MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")
WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION = "workbench_sql_projection.aggregate.oa_attachment_source_promotion.v1"
WORKBENCH_PANES = ("oa", "bank", "invoice")
WORKBENCH_FILTER_PLACEHOLDERS = {"", "--", "—"}
NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND = "no_oa_bank_batch_summary"
LOGGER = logging.getLogger(__name__)



def _execute_many(connection: Any, sql: str, params_seq: list[Any]) -> int:
    if not params_seq:
        return 0
    execute_many = getattr(connection, "execute_many", None)
    if callable(execute_many):
        return int(execute_many(sql, params_seq) or 0)
    affected = 0
    for params in params_seq:
        affected += int(connection.execute(sql, params) or 0)
    return affected


WORKBENCH_ALLOWED_FILTER_COLUMNS = {
    "oa": {"applicant", "projectName", "applicationType", "counterparty", "reconciliationStatus"},
    "bank": {"counterparty", "amount", "direction", "paymentAccount", "invoiceRelationStatus", "loanRepaymentDate"},
    "invoice": {"sellerName", "buyerName", "invoiceType"},
}
_TAX_OFFSET_ITEM_TYPES = {
    "output_items": "output",
    "input_plan_items": "input_plan",
    "certified_items": "certified",
    "certified_matched_rows": "certified_matched",
    "certified_outside_plan_rows": "certified_outside",
}
_TAX_OFFSET_PAYLOAD_KEYS = {item_type: payload_key for payload_key, item_type in _TAX_OFFSET_ITEM_TYPES.items()}


class PostgresBankReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection





class PostgresSummaryReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

class PostgresReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._summary_read_model_repository = PostgresSummaryReadModelRepository(connection)
        self._bank_read_model_repository = PostgresBankReadModelRepository(connection)

    def load_workbench_candidate_matches(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            "select candidate_key as key, payload, raw_payload from read_model.workbench_candidate_matches order by candidate_key"
        )
        values = {
            str(row.get("key")): payload
            for row in rows
            if (payload := _read_model_payload(row, drop_rebuildable_rows=True)) is not None
        }
        scope_rows = self._connection.fetch_all(
            """
            select
                to_char(scope_month, 'YYYY-MM') as scope_month,
                source_versions,
                completed_at::text as generated_at,
                request_id,
                reason
            from job.workbench_matching_dirty_scopes
            where tenant_id = 'default'
              and status = 'completed'
            order by scope_month
            """
        )
        scope_runs: dict[str, dict[str, Any]] = {}
        for row in scope_rows:
            scope_month = str(row.get("scope_month") or "").strip()
            if not MONTH_SCOPE_RE.match(scope_month):
                continue
            scope_runs[scope_month] = {
                "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
                "candidate_count": 0,
                "generated_at": str(row.get("generated_at") or ""),
                "request_id": str(row.get("request_id") or ""),
                "reason": str(row.get("reason") or ""),
            }
        result: dict[str, Any] = {}
        if values:
            result["candidates"] = values
        if scope_runs:
            result["schema_version"] = CANDIDATE_MATCH_SCHEMA_VERSION
            result["scope_runs"] = scope_runs
        return result

    def upsert_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        decisions: list[dict[str, Any]],
    ) -> None:
        def write(connection: Any) -> None:
            dirty_scope_keys: set[str] = set()
            for decision in decisions:
                payload = serialize_value(decision)
                scope_month = month_start(payload.get("scope_month"))
                if scope_month is not None:
                    dirty_scope_keys.add(str(scope_month)[:7])
                connection.execute(
                    """
                    insert into read_model.workbench_reconciliation_decisions(
                        tenant_id, scope_month, decision_id, decision_key, display_state, decision_status,
                        match_domain, match_shape, rule_code, rule_version, row_ids, row_types,
                        oa_row_ids, bank_row_ids, invoice_row_ids, amount, direction, cardinality,
                        payment_amount_closed, invoice_amount_closed, warnings, evidence, blockers,
                        conflict_set, explanation, source_versions, generated_at, raw_payload
                    )
                    values (
                        %s, %s::date, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s::timestamptz, %s
                    )
                    on conflict (tenant_id, decision_key) do update set
                        scope_month = excluded.scope_month,
                        decision_id = excluded.decision_id,
                        display_state = excluded.display_state,
                        decision_status = excluded.decision_status,
                        match_domain = excluded.match_domain,
                        match_shape = excluded.match_shape,
                        rule_code = excluded.rule_code,
                        rule_version = excluded.rule_version,
                        row_ids = excluded.row_ids,
                        row_types = excluded.row_types,
                        oa_row_ids = excluded.oa_row_ids,
                        bank_row_ids = excluded.bank_row_ids,
                        invoice_row_ids = excluded.invoice_row_ids,
                        amount = excluded.amount,
                        direction = excluded.direction,
                        cardinality = excluded.cardinality,
                        payment_amount_closed = excluded.payment_amount_closed,
                        invoice_amount_closed = excluded.invoice_amount_closed,
                        warnings = excluded.warnings,
                        evidence = excluded.evidence,
                        blockers = excluded.blockers,
                        conflict_set = excluded.conflict_set,
                        explanation = excluded.explanation,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        raw_payload = excluded.raw_payload,
                        consumed_by_relation_id = null,
                        suppressed_by_exception_case_id = null,
                        updated_at = now()
                    """,
                    (
                        text(tenant_id) or "default",
                        month_start(payload.get("scope_month")),
                        text(payload.get("decision_id")),
                        text(payload.get("decision_key")),
                        text(payload.get("display_state")),
                        text(payload.get("decision_status")),
                        text(payload.get("match_domain")),
                        text(payload.get("match_shape")),
                        text(payload.get("rule_code")),
                        text(payload.get("rule_version")),
                        text_list(payload.get("row_ids")),
                        _workbench_reconciliation_row_types(payload),
                        text_list(payload.get("oa_row_ids")),
                        text_list(payload.get("bank_row_ids")),
                        text_list(payload.get("invoice_row_ids")),
                        decimal_text(payload.get("amount")),
                        text(payload.get("direction")),
                        text(payload.get("cardinality")),
                        bool(payload.get("payment_amount_closed")),
                        bool(payload.get("invoice_amount_closed")),
                        jsonb(payload.get("warnings") if isinstance(payload.get("warnings"), list) else []),
                        jsonb(payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}),
                        jsonb(payload.get("blockers") if isinstance(payload.get("blockers"), list) else []),
                        jsonb(payload.get("conflict_set") if isinstance(payload.get("conflict_set"), list) else []),
                        text(payload.get("explanation")),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        text(payload.get("generated_at")),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
        run_in_transaction(self._connection, write)

    def list_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        statuses: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        where = ["tenant_id = %s", "scope_month = %s::date"]
        params: list[Any] = [text(tenant_id) or "default", month_start(scope_month)]
        if statuses:
            where.append("decision_status = any(%s)")
            params.append(sorted(str(status) for status in statuses))
        rows = self._connection.fetch_all(
            f"""
            select
                decision_key, scope_month, display_state, decision_status, match_domain, match_shape,
                rule_code, rule_version, row_ids, oa_row_ids, bank_row_ids, invoice_row_ids,
                amount, direction, payment_amount_closed, invoice_amount_closed, warnings, evidence,
                blockers, source_versions, consumed_by_relation_id, suppressed_by_exception_case_id,
                decision_id, explanation, raw_payload
            from read_model.workbench_reconciliation_decisions
            where {" and ".join(where)}
            order by decision_key
            """,
            tuple(params),
        )
        return [_workbench_reconciliation_decision_payload(row) for row in rows]

    def list_active_workbench_reconciliation_decisions_for_cleanup(
        self,
        *,
        tenant_id: str,
        scope_months: list[str] | None = None,
        decision_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        where = [
            "dec.tenant_id = %s",
            "dec.decision_status in ('proposed', 'paired', 'open')",
        ]
        params: list[Any] = [text(tenant_id) or "default"]
        normalized_scope_months = sorted(
            {month for month in (month_start(value) for value in list(scope_months or [])) if month}
        )
        normalized_decision_keys = sorted({value for value in (text(value) for value in list(decision_keys or [])) if value})
        if normalized_scope_months:
            where.append("dec.scope_month = any(%s::date[])")
            params.append(normalized_scope_months)
        if normalized_decision_keys:
            where.append("dec.decision_key = any(%s)")
            params.append(normalized_decision_keys)
        rows = self._connection.fetch_all(
            f"""
            select
                dec.decision_key,
                dec.scope_month,
                dec.display_state,
                dec.decision_status,
                dec.match_domain,
                dec.match_shape,
                dec.rule_code,
                dec.rule_version,
                dec.row_ids,
                dec.oa_row_ids,
                dec.bank_row_ids,
                dec.invoice_row_ids,
                dec.amount,
                dec.direction,
                dec.payment_amount_closed,
                dec.invoice_amount_closed,
                dec.warnings,
                dec.evidence,
                dec.blockers,
                dec.source_versions,
                dec.consumed_by_relation_id,
                dec.suppressed_by_exception_case_id,
                dec.decision_id,
                dec.explanation,
                dec.raw_payload,
                dec.updated_at,
                coalesce(active_relation_overlaps.items, '[]'::jsonb) as active_relation_overlaps,
                coalesce(submitted_no_oa_batch_overlaps.items, '[]'::jsonb) as submitted_no_oa_batch_overlaps
            from read_model.workbench_reconciliation_decisions dec
            left join lateral (
                select jsonb_agg(
                    jsonb_build_object(
                        'case_id', rel.case_id,
                        'relation_mode', rel.relation_mode,
                        'month_scope', coalesce(to_char(rel.month_scope, 'YYYY-MM'), 'all'),
                        'row_ids', rel.row_ids,
                        'row_types', rel.row_types,
                        'overlap_row_ids', overlap_rows.overlap_row_ids
                    )
                    order by rel.case_id
                ) as items
                from app.workbench_pair_relations rel
                cross join lateral (
                    select array_agg(decision_row_id order by decision_row_id) as overlap_row_ids
                    from unnest(dec.row_ids) decision_row_id
                    where decision_row_id = any(rel.row_ids)
                ) overlap_rows
                where rel.status = 'active'
                  and rel.row_ids && dec.row_ids
                  and cardinality(overlap_rows.overlap_row_ids) > 0
                  and (
                    rel.month_scope is null
                    or rel.month_scope between (dec.scope_month - interval '2 months')::date
                                           and (dec.scope_month + interval '2 months')::date
                  )
            ) active_relation_overlaps on true
            left join lateral (
                select jsonb_agg(
                    jsonb_build_object(
                        'batch_id', batch.batch_id,
                        'batch_type', batch.raw_payload->'normalized_payload'->>'batch_type',
                        'batch_label', batch.raw_payload->'normalized_payload'->>'batch_label',
                        'status', batch.status,
                        'scope_month', coalesce(to_char(batch.scope_month, 'YYYY-MM'), 'all'),
                        'bank_transaction_ids', batch.bank_transaction_ids,
                        'overlap_row_ids', overlap_rows.overlap_row_ids
                    )
                    order by batch.batch_id
                ) as items
                from app.no_oa_bank_batches batch
                cross join lateral (
                    select array_agg(decision_bank_row_id order by decision_bank_row_id) as overlap_row_ids
                    from unnest(dec.bank_row_ids) decision_bank_row_id
                    where decision_bank_row_id = any(batch.bank_transaction_ids)
                ) overlap_rows
                where batch.status = 'submitted'
                  and batch.bank_transaction_ids && dec.bank_row_ids
                  and cardinality(overlap_rows.overlap_row_ids) > 0
                  and (
                    batch.scope_month is null
                    or batch.scope_month between (dec.scope_month - interval '2 months')::date
                                             and (dec.scope_month + interval '2 months')::date
                  )
            ) submitted_no_oa_batch_overlaps on true
            where {" and ".join(where)}
            order by dec.scope_month, dec.decision_key
            """,
            tuple(params),
        )
        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = _workbench_reconciliation_decision_payload(row)
            payload["active_relation_overlaps"] = (
                row.get("active_relation_overlaps") if isinstance(row.get("active_relation_overlaps"), list) else []
            )
            payload["submitted_no_oa_batch_overlaps"] = (
                row.get("submitted_no_oa_batch_overlaps")
                if isinstance(row.get("submitted_no_oa_batch_overlaps"), list)
                else []
            )
            payload["updated_at"] = text(row.get("updated_at"))
            payloads.append(payload)
        return payloads

    def expire_workbench_reconciliation_decisions_by_keys(
        self,
        *,
        tenant_id: str,
        decision_keys: list[str],
        reason: str,
        actor: str = "repair_workbench_reconciliation_decisions",
    ) -> dict[str, Any]:
        normalized_decision_keys = sorted({value for value in (text(value) for value in list(decision_keys or [])) if value})
        if not normalized_decision_keys:
            return {"expired_count": 0, "scope_keys": []}

        def write(connection: Any) -> dict[str, Any]:
            rows = connection.fetch_all(
                """
                with expired as (
                    update read_model.workbench_reconciliation_decisions
                    set decision_status = 'expired',
                        raw_payload = raw_payload || jsonb_build_object(
                            'expired_reason', %s::text,
                            'expired_by', %s::text
                        ),
                        updated_at = now()
                    where tenant_id = %s::text
                      and decision_key = any(%s::text[])
                      and decision_status in ('proposed', 'paired', 'open')
                    returning to_char(scope_month, 'YYYY-MM') as scope_key
                )
                select scope_key, count(*)::bigint as expired_count
                from expired
                group by scope_key
                order by scope_key
                """,
                (
                    text(reason) or "invalid_workbench_reconciliation_decision",
                    text(actor) or "repair_workbench_reconciliation_decisions",
                    text(tenant_id) or "default",
                    normalized_decision_keys,
                ),
            )
            scope_keys = [str(row.get("scope_key") or "").strip() for row in rows if str(row.get("scope_key") or "").strip()]
            expired_count = sum(int_value(row.get("expired_count"), 0) for row in rows)
            return {"expired_count": expired_count, "scope_keys": scope_keys}

        result: dict[str, Any] = {"expired_count": 0, "scope_keys": []}

        def capture(connection: Any) -> None:
            nonlocal result
            result = write(connection)

        run_in_transaction(self._connection, capture)
        return result

    def consume_workbench_reconciliation_decisions_by_row_ids(
        self,
        *,
        tenant_id: str,
        row_ids: list[str],
        relation_id: str,
    ) -> int:
        return int(
            self._connection.execute(
                """
                update read_model.workbench_reconciliation_decisions
                set decision_status = 'consumed',
                    consumed_by_relation_id = %s,
                    updated_at = now()
                where tenant_id = %s
                  and decision_status in ('proposed', 'paired', 'open')
                  and row_ids && %s
                """,
                (relation_id, text(tenant_id) or "default", text_list(row_ids)),
            )
            or 0
        )

    def suppress_workbench_reconciliation_decisions_by_row_ids(
        self,
        *,
        tenant_id: str,
        row_ids: list[str],
        exception_case_id: str,
    ) -> int:
        return int(
            self._connection.execute(
                """
                update read_model.workbench_reconciliation_decisions
                set decision_status = 'suppressed',
                    suppressed_by_exception_case_id = %s,
                    updated_at = now()
                where tenant_id = %s
                  and decision_status in ('proposed', 'paired', 'open')
                  and row_ids && %s
                """,
                (exception_case_id, text(tenant_id) or "default", text_list(row_ids)),
            )
            or 0
        )

    def expire_stale_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        scope_months: list[str],
        source_versions: dict[str, object],
    ) -> int:
        normalized_scope_months = sorted({month_start(month) for month in scope_months if month_start(month)})

        def write(connection: Any) -> int:
            affected = int(
                connection.execute(
                """
                update read_model.workbench_reconciliation_decisions
                set decision_status = 'expired',
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = any(%s::date[])
                  and decision_status in ('proposed', 'paired', 'open')
                  and not (source_versions @> %s)
                """,
                (
                    text(tenant_id) or "default",
                    normalized_scope_months,
                    jsonb(source_versions),
                ),
            )
            or 0
            )
            return affected

        result = 0

        def capture(connection: Any) -> None:
            nonlocal result
            result = write(connection)

        run_in_transaction(self._connection, capture)
        return result

    def expire_missing_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        active_decision_keys: list[str],
    ) -> int:
        normalized_scope_month = month_start(scope_month)

        def write(connection: Any) -> int:
            affected = int(
                connection.execute(
                """
                update read_model.workbench_reconciliation_decisions
                set decision_status = 'expired',
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = %s::date
                  and decision_status in ('proposed', 'paired', 'open')
                  and not (decision_key = any(%s))
                """,
                (
                    text(tenant_id) or "default",
                    normalized_scope_month,
                    text_list(active_decision_keys),
                ),
            )
            or 0
            )
            return affected

        result = 0

        def capture(connection: Any) -> None:
            nonlocal result
            result = write(connection)

        run_in_transaction(self._connection, capture)
        return result

    def mark_workbench_matching_dirty_scopes(
        self,
        *,
        tenant_id: str,
        scope_months: list[str],
        reason: str,
        source_versions: dict[str, object],
        debounce_seconds: int,
    ) -> list[str]:
        normalized_months = sorted({str(month)[:7] for month in scope_months if str(month or "").strip()})

        def write(connection: Any) -> None:
            for scope_month in normalized_months:
                connection.execute(
                    """
                    insert into job.workbench_matching_dirty_scopes(
                        tenant_id, scope_month, reason, status, available_at, source_versions, raw_payload
                    )
                    values (
                        %s, %s::date, %s, 'dirty', now() + (%s::text || ' seconds')::interval, %s, %s
                    )
                    on conflict (tenant_id, scope_month) do update set
                        reason = excluded.reason,
                        status = 'dirty',
                        available_at = greatest(job.workbench_matching_dirty_scopes.available_at, excluded.available_at),
                        source_versions = job.workbench_matching_dirty_scopes.source_versions || excluded.source_versions,
                        lease_owner = null,
                        lease_expires_at = null,
                        updated_at = now()
                    """,
                    (
                        text(tenant_id) or "default",
                        month_start(scope_month),
                        text(reason),
                        max(0, int_value(debounce_seconds, 60)),
                        jsonb(source_versions),
                        jsonb({"reason": reason, "source_versions": source_versions}),
                    ),
                )

        run_in_transaction(self._connection, write)
        return normalized_months

    def mark_stale_workbench_matching_completed_scopes(
        self,
        *,
        tenant_id: str,
        source_versions: dict[str, object],
        reason: str,
        debounce_seconds: int,
        limit: int | None = None,
    ) -> list[str]:
        normalized_tenant = text(tenant_id) or "default"
        normalized_source_versions = dict(source_versions or {})
        if not normalized_source_versions:
            return []
        resolved_limit = max(1, int_value(limit, 100)) if limit is not None else 100
        resolved_debounce_seconds = max(0, int_value(debounce_seconds, 0))

        def write(connection: Any) -> list[dict[str, Any]]:
            return connection.fetch_all(
                """
                with stale as (
                    select id
                    from job.workbench_matching_dirty_scopes
                    where tenant_id = %s
                      and status = 'completed'
                      and not (coalesce(source_versions, '{}'::jsonb) @> %s)
                    order by completed_at nulls first, scope_month
                    limit %s
                    for update skip locked
                )
                update job.workbench_matching_dirty_scopes dirty
                set reason = %s,
                    status = 'dirty',
                    available_at = now() + (%s::text || ' seconds')::interval,
                    source_versions = coalesce(dirty.source_versions, '{}'::jsonb) || %s,
                    lease_owner = null,
                    lease_expires_at = null,
                    updated_at = now()
                from stale
                where dirty.id = stale.id
                returning to_char(dirty.scope_month, 'YYYY-MM') as scope_month
                """,
                (
                    normalized_tenant,
                    jsonb(normalized_source_versions),
                    resolved_limit,
                    text(reason),
                    resolved_debounce_seconds,
                    jsonb(normalized_source_versions),
                ),
            )

        rows = run_in_transaction(self._connection, write)
        return [str(row.get("scope_month")) for row in rows if row.get("scope_month")]

    def claim_workbench_matching_dirty_scopes(
        self,
        *,
        tenant_id: str,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        request_id: str | None = None,
    ) -> list[str]:
        resolved_request_id = text(request_id) or text(worker_id) or "worker"
        normalized_tenant = text(tenant_id) or "default"
        normalized_worker = text(worker_id) or "worker"

        def write(connection: Any) -> list[dict[str, Any]]:
            rows = connection.fetch_all(
                """
                with due as (
                    select id
                    from job.workbench_matching_dirty_scopes
                    where tenant_id = %s
                      and (
                        status in ('dirty', 'retry') and available_at <= now()
                        or status = 'processing' and lease_expires_at <= now()
                      )
                    order by available_at, scope_month
                    limit %s
                    for update skip locked
                )
                update job.workbench_matching_dirty_scopes dirty
                set status = 'processing',
                    lease_owner = %s,
                    lease_expires_at = now() + (%s::text || ' seconds')::interval,
                    request_id = %s || ':' || to_char(dirty.scope_month, 'YYYY-MM'),
                    started_at = now(),
                    completed_at = null,
                    failed_at = null,
                    duration_ms = null,
                    error_summary = null,
                    updated_at = now()
                from due
                where dirty.id = due.id
                returning to_char(dirty.scope_month, 'YYYY-MM') as scope_month,
                          dirty.request_id,
                          dirty.source_versions
                """,
                (
                    normalized_tenant,
                    max(1, int_value(limit, 1)),
                    normalized_worker,
                    max(1, int_value(lease_seconds, 600)),
                    resolved_request_id,
                ),
            )
            for row in rows:
                connection.execute(
                    """
                    insert into app.matching_runs(
                        tenant_id, run_id, request_id, scope_month, triggered_by,
                        executed_at, started_at, status, source_versions, raw_payload
                    )
                    values (%s, %s, %s, %s::date, %s, now(), now(), 'running', %s, %s)
                    on conflict (tenant_id, request_id) where request_id is not null do update set
                        started_at = excluded.started_at,
                        status = 'running',
                        source_versions = excluded.source_versions,
                        updated_at = now()
                    """,
                    (
                        normalized_tenant,
                        text(row.get("request_id")),
                        text(row.get("request_id")),
                        month_start(row.get("scope_month")),
                        normalized_worker,
                        jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
                        jsonb({"scope_month": row.get("scope_month"), "worker_id": normalized_worker}),
                    ),
                )
            return rows

        rows = run_in_transaction(self._connection, write)
        return [str(row.get("scope_month")) for row in rows if row.get("scope_month")]

    def complete_workbench_matching_dirty_scope(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        source_versions: dict[str, object],
        worker_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        normalized_tenant = text(tenant_id) or "default"
        normalized_worker = text(worker_id)
        normalized_request = text(request_id)
        if not normalized_worker:
            raise ValueError("worker_id is required to complete a workbench matching dirty scope.")
        if not normalized_request:
            raise ValueError("request_id is required to complete a workbench matching dirty scope.")

        def write(connection: Any) -> None:
            row = connection.fetch_one(
                """
                update job.workbench_matching_dirty_scopes
                set status = 'completed',
                    completed_at = now(),
                    failed_at = null,
                    duration_ms = greatest(0, floor(extract(epoch from (now() - started_at)) * 1000)::integer),
                    source_versions = %s,
                    lease_owner = null,
                    lease_expires_at = null,
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = %s::date
                  and status = 'processing'
                  and lease_owner = %s
                  and request_id = %s
                returning request_id, duration_ms
                """,
                (
                    jsonb(source_versions),
                    normalized_tenant,
                    month_start(scope_month),
                    normalized_worker,
                    normalized_request,
                ),
            )
            if not isinstance(row, dict):
                raise RuntimeError("Workbench matching dirty scope is not actively leased.")
            connection.execute(
                """
                update app.matching_runs
                set status = 'completed',
                    completed_at = now(),
                    failed_at = null,
                    duration_ms = %s,
                    source_versions = %s,
                    updated_at = now()
                where tenant_id = %s and request_id = %s
                """,
                (
                    int_value(row.get("duration_ms"), 0),
                    jsonb(source_versions),
                    normalized_tenant,
                    text(row.get("request_id")),
                ),
            )

        run_in_transaction(self._connection, write)

    def fail_workbench_matching_dirty_scope(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        error: str,
        retry_delay_seconds: int | None,
        retry_max_attempts: int,
        retry_backoff_seconds: list[int],
        worker_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        delay_seconds = int_value(retry_delay_seconds, 0)
        backoff_sql = _retry_backoff_case_sql(retry_backoff_seconds)
        normalized_tenant = text(tenant_id) or "default"
        normalized_worker = text(worker_id)
        normalized_request = text(request_id)
        if not normalized_worker:
            raise ValueError("worker_id is required to fail a workbench matching dirty scope.")
        if not normalized_request:
            raise ValueError("request_id is required to fail a workbench matching dirty scope.")

        def write(connection: Any) -> None:
            row = connection.fetch_one(
                f"""
                update job.workbench_matching_dirty_scopes
                set attempt_count = attempt_count + 1,
                    status = case when attempt_count + 1 >= %s then 'failed' else 'retry' end,
                    last_error = %s,
                    failed_at = now(),
                    completed_at = null,
                    duration_ms = greatest(0, floor(extract(epoch from (now() - started_at)) * 1000)::integer),
                    error_summary = %s,
                    available_at = now() + (
                        (case when %s > 0 then %s else {backoff_sql} end)::text || ' seconds'
                    )::interval,
                    lease_owner = null,
                    lease_expires_at = null,
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = %s::date
                  and status = 'processing'
                  and lease_owner = %s
                  and request_id = %s
                returning request_id, duration_ms, source_versions
                """,
                (
                    max(1, int_value(retry_max_attempts, 5)),
                    text(error),
                    text(error),
                    max(0, delay_seconds),
                    max(0, delay_seconds),
                    normalized_tenant,
                    month_start(scope_month),
                    normalized_worker,
                    normalized_request,
                ),
            )
            if not isinstance(row, dict):
                raise RuntimeError("Workbench matching dirty scope is not actively leased.")
            connection.execute(
                """
                update app.matching_runs
                set status = 'failed',
                    failed_at = now(),
                    duration_ms = %s,
                    source_versions = %s,
                    error_summary = %s,
                    updated_at = now()
                where tenant_id = %s and request_id = %s
                """,
                (
                    int_value(row.get("duration_ms"), 0),
                    jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
                    text(error),
                    normalized_tenant,
                    text(row.get("request_id")),
                ),
            )

        run_in_transaction(self._connection, write)

    def list_workbench_matching_dirty_scopes(self, *, tenant_id: str) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select tenant_id, to_char(scope_month, 'YYYY-MM') as scope_month, reason, status,
                   attempt_count, last_error, available_at, lease_owner, lease_expires_at,
                   request_id, started_at, completed_at, failed_at, duration_ms, source_versions, error_summary
            from job.workbench_matching_dirty_scopes
            where tenant_id = %s
            order by scope_month
            """,
            (text(tenant_id) or "default",),
        )

    def list_workbench_matching_runs(self, *, tenant_id: str) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select to_char(scope_month, 'YYYY-MM') as scope_month, request_id, started_at, completed_at,
                   failed_at, duration_ms, status, source_versions, error_summary
            from app.matching_runs
            where tenant_id = %s and request_id is not null
            order by started_at, request_id
            """,
            (text(tenant_id) or "default",),
        )

    def save_workbench_candidate_matches(self, snapshot: dict[str, Any], *, changed_scope_months: set[str] | None = None) -> None:
        def write(connection: Any) -> None:
            candidates = snapshot.get("candidates") if isinstance(snapshot, dict) else None
            normalized_months = {str(month)[:7] for month in changed_scope_months or set() if str(month or "").strip()}
            scope_runs = snapshot.get("scope_runs") if isinstance(snapshot, dict) else None
            incoming_versions_by_month = {
                str(month)[:7]: _source_version_value(
                    run.get("source_versions") if isinstance(run, dict) else {}
                )
                for month, run in iter_mapping(scope_runs)
                if str(month or "").strip()
            }
            stale_months: set[str] = set()
            for scope_month in sorted(normalized_months):
                incoming_source_version = incoming_versions_by_month.get(scope_month)
                existing_row = connection.fetch_one(
                    """
                    select max((source_versions->>'source_version')::bigint) as source_version
                    from read_model.workbench_candidate_matches
                    where to_char(scope_month, 'YYYY-MM') = %s
                      and source_versions ? 'source_version'
                    """,
                    (scope_month,),
                )
                existing_source_version = _source_version_value(
                    {"source_version": existing_row.get("source_version")} if isinstance(existing_row, dict) else {}
                )
                if (
                    incoming_source_version is not None
                    and existing_source_version is not None
                    and incoming_source_version < existing_source_version
                ):
                    stale_months.add(scope_month)
                    continue
                connection.execute(
                    "delete from read_model.workbench_candidate_matches where to_char(scope_month, 'YYYY-MM') = %s",
                    (scope_month,),
                )
            for candidate_key, payload in iter_mapping(candidates):
                scope_month = month_start(payload.get("scope_month") or payload.get("month"))
                normalized_scope_month = str(scope_month or "")[:7]
                if normalized_months and normalized_scope_month not in normalized_months:
                    continue
                if normalized_scope_month in stale_months:
                    continue
                connection.execute(
                    """
                    insert into read_model.workbench_candidate_matches(
                        candidate_key, scope_month, status, row_ids, confidence, source_versions,
                        generated_at, cache_status, payload, raw_payload
                    )
                    values (%s, %s::date, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s)
                    on conflict (candidate_key) do update set
                        scope_month = excluded.scope_month,
                        status = excluded.status,
                        row_ids = excluded.row_ids,
                        confidence = excluded.confidence,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        candidate_key,
                        scope_month,
                        text(payload.get("status") or "active"),
                        text_list(payload.get("row_ids")),
                        decimal_text(payload.get("confidence")),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        text(payload.get("generated_at")),
                        text(payload.get("cache_status") or "fresh"),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

def _cost_statistics_payload_from_rows(
    *,
    scope_key: str,
    parent_payload: dict[str, Any],
    parent_row: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    parent_model_payload = parent_payload.get("payload") if isinstance(parent_payload.get("payload"), dict) else parent_payload
    project_scope, scope_month_text = _parse_cost_statistics_scope_parts(scope_key, payload=parent_model_payload)
    if rows:
        scope_month_text = text(rows[0].get("scope_month")) or scope_month_text
    month = scope_month_text[:7] if scope_month_text and scope_month_text != "all" else text(parent_model_payload.get("month")) or scope_month_text
    time_rows: list[dict[str, Any]] = []
    project_groups: dict[str, dict[str, Any]] = {}
    expense_groups: dict[str, dict[str, Any]] = {}
    total_amount = Decimal("0")
    for index, db_row in enumerate(rows):
        payload = _read_model_payload(db_row)
        row_payload_value = deepcopy(payload) if isinstance(payload, dict) else {}
        amount = _decimal_or_zero(db_row.get("amount") or row_payload_value.get("amount"))
        total_amount += amount
        project_name = text(db_row.get("project_name") or row_payload_value.get("project_name")) or "未归集项目"
        expense_type = text(db_row.get("expense_type") or row_payload_value.get("expense_type")) or "未分类"
        transaction_id = text(db_row.get("transaction_id") or row_payload_value.get("transaction_id")) or f"row-{index}"
        normalized_row = {
            **row_payload_value,
            "transaction_id": transaction_id,
            "group_id": text(db_row.get("group_id") or row_payload_value.get("group_id")),
            "trade_time": text(db_row.get("trade_time_text") or row_payload_value.get("trade_time") or db_row.get("trade_date")),
            "direction": text(db_row.get("direction") or row_payload_value.get("direction")),
            "project_name": project_name,
            "project_id": text(db_row.get("project_id") or row_payload_value.get("project_id")),
            "expense_type": expense_type,
            "expense_content": text(db_row.get("expense_content") or row_payload_value.get("expense_content")),
            "amount": _format_decimal(amount),
            "counterparty_name": text(db_row.get("counterparty_name") or row_payload_value.get("counterparty_name")),
            "payment_account_label": text(db_row.get("payment_account_label") or row_payload_value.get("payment_account_label")),
            "remark": text(db_row.get("remark") or row_payload_value.get("remark")),
            "oa_applicant": text(db_row.get("oa_applicant") or row_payload_value.get("oa_applicant")),
        }
        time_rows.append(normalized_row)
        project_bucket = project_groups.setdefault(
            project_name,
            {"project_name": project_name, "total_amount": Decimal("0"), "transaction_count": 0, "expense_types": set()},
        )
        project_bucket["total_amount"] += amount
        project_bucket["transaction_count"] += 1
        project_bucket["expense_types"].add(expense_type)
        expense_bucket = expense_groups.setdefault(
            expense_type,
            {"expense_type": expense_type, "total_amount": Decimal("0"), "transaction_count": 0, "projects": set()},
        )
        expense_bucket["total_amount"] += amount
        expense_bucket["transaction_count"] += 1
        expense_bucket["projects"].add(project_name)
    return {
        "month": month,
        "project_scope": project_scope,
        "summary": {
            "row_count": len(time_rows),
            "transaction_count": len(time_rows),
            "total_amount": _format_decimal(total_amount),
        },
        "time_rows": time_rows,
        "project_rows": [
            {
                "project_name": bucket["project_name"],
                "total_amount": _format_decimal(bucket["total_amount"]),
                "transaction_count": bucket["transaction_count"],
                "expense_type_count": len(bucket["expense_types"]),
            }
            for bucket in sorted(project_groups.values(), key=lambda item: (-item["total_amount"], item["project_name"]))
        ],
        "expense_type_rows": [
            {
                "expense_type": bucket["expense_type"],
                "total_amount": _format_decimal(bucket["total_amount"]),
                "transaction_count": bucket["transaction_count"],
                "project_count": len(bucket["projects"]),
            }
            for bucket in sorted(expense_groups.values(), key=lambda item: (-item["total_amount"], item["expense_type"]))
        ],
        "generated_at": text(parent_row.get("generated_at") or parent_payload.get("generated_at")),
    }


def _parse_cost_statistics_scope_parts(scope_key: str, *, payload: dict[str, Any] | None = None) -> tuple[str, str]:
    normalized = text(scope_key) or "all"
    payload = payload if isinstance(payload, dict) else {}
    if normalized.startswith("active:"):
        return "active", normalized.split(":", 1)[1] or "all"
    project_scope = text(payload.get("project_scope")) or text(payload.get("projectScope")) or "all"
    scope_month = text(payload.get("month")) or text(payload.get("scope_month")) or normalized
    return project_scope, scope_month


def _is_cost_statistics_parent_scope(scope_key: str, *, payload: dict[str, Any] | None = None) -> bool:
    payload = payload if isinstance(payload, dict) else {}
    if str(scope_key or "").startswith("active:"):
        return True
    return any(isinstance(payload.get(key), list) for key in ("time_rows", "project_rows", "expense_type_rows"))


def _tax_offset_payload_from_items(*, parent_payload: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload = deepcopy(parent_payload)
    for key in _TAX_OFFSET_ITEM_TYPES:
        payload[key] = []
    for row in rows:
        item_type = text(row.get("item_type"))
        payload_key = _TAX_OFFSET_PAYLOAD_KEYS.get(item_type or "")
        if payload_key is None:
            continue
        item_payload = _read_model_payload(row)
        if isinstance(item_payload, dict):
            payload[payload_key].append(item_payload)
    return payload


def _tax_offset_item_count(payload: dict[str, Any]) -> int:
    total = 0
    for key in _TAX_OFFSET_ITEM_TYPES:
        value = payload.get(key)
        if isinstance(value, list):
            total += len(value)
    return total


def _turnover_ledger_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    if isinstance(payload, dict):
        return payload
    return {
        "relation_id": text(row.get("relation_id")),
        "family": text(row.get("family")),
        "status": text(row.get("status")),
        "balance_amount": decimal_text(row.get("amount")) or "0.00",
    }


def _shared_source_versions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    versions: dict[str, Any] = {}
    for row in rows:
        row_versions = row.get("source_versions")
        if not isinstance(row_versions, dict):
            return {}
        if not versions:
            versions = dict(row_versions)
            continue
        if row_versions != versions:
            return {}
    return versions


def _turnover_ledger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pending_repayment = Decimal("0")
    repaid = Decimal("0")
    pending_collection = Decimal("0")
    collected = Decimal("0")
    closed = Decimal("0")
    suggested_count = 0
    conflict_count = 0
    for row in rows:
        if any(
            row.get(key) is not None
            for key in (
                "pending_repayment_amount",
                "repaid_amount",
                "pending_collection_amount",
                "collected_amount",
                "closed_amount",
            )
        ):
            pending_repayment += _decimal_or_zero(row.get("pending_repayment_amount"))
            repaid += _decimal_or_zero(row.get("repaid_amount"))
            pending_collection += _decimal_or_zero(row.get("pending_collection_amount"))
            collected += _decimal_or_zero(row.get("collected_amount"))
            closed += _decimal_or_zero(row.get("closed_amount"))
            if row.get("status") == "suggested":
                suggested_count += 1
            if row.get("status") == "conflict":
                conflict_count += 1
            continue
        principal = _decimal_or_zero(row.get("principal_amount"))
        settled = _decimal_or_zero(row.get("settled_amount"))
        balance = _decimal_or_zero(row.get("balance_amount"))
        business_type = text(row.get("business_type")) or ""
        if business_type == "borrow_in":
            pending_repayment += max(balance, Decimal("0"))
            repaid += settled
        elif business_type in {"borrow_out", "business_receivable"}:
            pending_collection += max(balance, Decimal("0"))
            collected += settled
        if balance == Decimal("0") and row.get("status") in {"deterministic", "confirmed"}:
            closed += principal
        if row.get("status") == "suggested":
            suggested_count += 1
        if row.get("status") == "conflict":
            conflict_count += 1
    return {
        "pending_repayment_amount": _format_decimal(pending_repayment),
        "repaid_amount": _format_decimal(repaid),
        "pending_collection_amount": _format_decimal(pending_collection),
        "collected_amount": _format_decimal(collected),
        "closed_amount": _format_decimal(closed),
        "suggested_count": suggested_count,
        "conflict_count": conflict_count,
        "row_count": len(rows),
    }


def _turnover_ledger_family_summary(family: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _turnover_ledger_summary(rows)
    pending_amount = _decimal_or_zero(summary.get("pending_repayment_amount")) + _decimal_or_zero(
        summary.get("pending_collection_amount")
    )
    labels = {"personal": "个人往来", "company": "公司往来", "bank": "银行往来", "business": "业务往来"}
    return {
        "family": family,
        "label": labels.get(family, family),
        "pending_repayment_amount": summary["pending_repayment_amount"],
        "repaid_amount": summary["repaid_amount"],
        "pending_collection_amount": summary["pending_collection_amount"],
        "collected_amount": summary["collected_amount"],
        "pending_amount": _format_decimal(pending_amount),
        "closed_amount": summary["closed_amount"],
        "row_count": summary["row_count"],
    }


def _date_text(value: Any) -> str | None:
    normalized = text(value)
    if not normalized:
        return None
    if len(normalized) >= 10 and normalized[4] == "-" and normalized[7] == "-":
        return normalized[:10]
    return month_start(normalized)


def _decimal_or_zero(value: Any) -> Decimal:
    if value in (None, "", "—", "--"):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.01"))
    return format(normalized, "f")


def _dedupe_workbench_payload_groups(payload: dict[str, Any]) -> None:
    for zone in ("paired", "open"):
        section = payload.get(zone)
        if not isinstance(section, dict):
            continue
        groups = section.get("groups")
        if not isinstance(groups, list):
            continue
        deduped: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        seen_row_sets: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            group_id = text(group.get("group_id") or group.get("id")) or f"{zone}:{index}"
            group_key = (zone, group_id)
            if group_key in seen_keys:
                continue
            row_identity = _workbench_group_row_identity(group)
            if row_identity:
                row_key = (zone, row_identity)
                if row_key in seen_row_sets:
                    continue
                seen_row_sets.add(row_key)
            seen_keys.add(group_key)
            deduped.append(group)
        section["groups"] = deduped



def _workbench_row_id(row: dict[str, Any]) -> str | None:
    return text(row.get("id") or row.get("row_id"))


def _is_workbench_summary_display_row(row: dict[str, Any], pane: str) -> bool:
    return pane == "bank" and (
        text(row.get("row_role")) == "summary"
        or text(row.get("source_kind")) == NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND
    )


def _empty_workbench_row_counts() -> dict[str, int]:
    return {"oa": 0, "bank": 0, "invoice": 0, "rows": 0}


def _workbench_group_fact_row_counts(group: dict[str, Any]) -> dict[str, int]:
    counts = _empty_workbench_row_counts()
    seen: set[tuple[str, str]] = set()
    for pane, row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
        if pane not in WORKBENCH_PANES or row_role == "summary":
            continue
        row_id = _workbench_row_id(row)
        if row_id is None:
            continue
        row_key = (pane, row_id)
        if row_key in seen:
            continue
        seen.add(row_key)
        counts[pane] += 1
        counts["rows"] += 1
    return counts


def _workbench_panes_with_summary_display_rows(group: dict[str, Any]) -> set[str]:
    panes: set[str] = set()
    for pane, row_role, _row_index, _row in _iter_typed_group_rows_with_metadata(group):
        if row_role == "summary":
            panes.add(pane)
    return panes


def _workbench_group_display_row_counts(group: dict[str, Any]) -> dict[str, int]:
    counts = _empty_workbench_row_counts()
    for pane, row_key in (("oa", "oa_rows"), ("bank", "bank_rows"), ("invoice", "invoice_rows")):
        rows = group.get(row_key)
        if isinstance(rows, list):
            counts[pane] = sum(1 for row in rows if isinstance(row, dict))
            counts["rows"] += counts[pane]
    return counts


def _normalize_workbench_row_counts(value: Any, fallback: dict[str, int]) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    counts = {
        "oa": int_value(source.get("oa"), fallback.get("oa", 0)),
        "bank": int_value(source.get("bank"), fallback.get("bank", 0)),
        "invoice": int_value(source.get("invoice"), fallback.get("invoice", 0)),
        "rows": 0,
    }
    counts["rows"] = int_value(source.get("rows"), counts["oa"] + counts["bank"] + counts["invoice"])
    return counts


def _with_workbench_group_counts(group: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(group)
    normalized["row_counts"] = _workbench_group_fact_row_counts(normalized)
    normalized["display_row_counts"] = _workbench_group_display_row_counts(normalized)
    normalized["row_count"] = normalized["row_counts"]["rows"]
    return normalized


def _empty_workbench_zone_counts() -> dict[str, dict[str, int]]:
    return {
        "paired": {"groups": 0, "oa": 0, "bank": 0, "invoice": 0, "rows": 0},
        "open": {"groups": 0, "oa": 0, "bank": 0, "invoice": 0, "rows": 0},
    }


def _normalize_workbench_summary_counts(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    zone_counts = normalized.get("zone_counts")
    if not isinstance(zone_counts, dict):
        zone_counts = _empty_workbench_zone_counts()
        zone_counts["paired"]["groups"] = int_value(normalized.get("paired_count"), 0)
        zone_counts["open"]["groups"] = int_value(normalized.get("open_count"), 0)
    else:
        merged = _empty_workbench_zone_counts()
        for zone in ("paired", "open"):
            zone_payload = zone_counts.get(zone)
            if not isinstance(zone_payload, dict):
                continue
            merged[zone]["groups"] = int_value(zone_payload.get("groups"), 0)
            merged[zone]["oa"] = int_value(zone_payload.get("oa"), 0)
            merged[zone]["bank"] = int_value(zone_payload.get("bank"), 0)
            merged[zone]["invoice"] = int_value(zone_payload.get("invoice"), 0)
            merged[zone]["rows"] = int_value(
                zone_payload.get("rows"),
                merged[zone]["oa"] + merged[zone]["bank"] + merged[zone]["invoice"],
            )
        zone_counts = merged
    normalized["zone_counts"] = zone_counts
    return normalized



def _normalize_workbench_invoice_display_fields(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if text(normalized.get("type")) != "invoice":
        return normalized
    detail_fields = normalized.get("detail_fields")
    detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
    summary_fields = normalized.get("summary_fields")
    summary_fields = summary_fields if isinstance(summary_fields, dict) else {}

    _set_workbench_display_value(
        normalized,
        "invoice_code",
        detail_fields.get("发票代码"),
        summary_fields.get("发票代码"),
    )
    _set_workbench_display_value(
        normalized,
        "invoice_no",
        normalized.get("digital_invoice_no"),
        detail_fields.get("发票号码"),
        detail_fields.get("数电发票号码"),
        summary_fields.get("发票号码"),
        summary_fields.get("数电发票号码"),
    )
    _set_workbench_display_value(
        normalized,
        "digital_invoice_no",
        detail_fields.get("数电发票号码"),
        summary_fields.get("数电发票号码"),
    )
    _set_workbench_display_value(
        normalized,
        "tax_rate",
        summary_fields.get("税率"),
        detail_fields.get("税率"),
        detail_fields.get("tax_rate"),
    )
    _set_workbench_display_value(
        normalized,
        "tax_amount",
        summary_fields.get("税额"),
        detail_fields.get("税额"),
        detail_fields.get("tax_amount"),
    )
    return normalized


def _set_workbench_display_value(row: dict[str, Any], key: str, *fallback_values: Any) -> None:
    current = text(row.get(key))
    if current and current not in WORKBENCH_FILTER_PLACEHOLDERS:
        return
    row[key] = _first_workbench_display_value(*fallback_values)


def _first_workbench_display_value(*values: Any) -> str:
    for value in values:
        normalized = text(value)
        if normalized and normalized not in WORKBENCH_FILTER_PLACEHOLDERS:
            return normalized
    return "—"


def _workbench_group_sort_keys(group: dict[str, Any]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for pane_id in ("oa", "bank", "invoice"):
        values = sorted(
            value
            for row_type, row in _iter_typed_group_rows(group)
            if row_type == pane_id
            if (value := _workbench_row_sort_value(row, pane_id)) is not None
        )
        result[f"{pane_id}_sort_min"] = values[0] if values else None
        result[f"{pane_id}_sort_max"] = values[-1] if values else None
    return result


def _workbench_row_sort_value(row: dict[str, Any], pane_id: str) -> str | None:
    table_values = row.get("table_values")
    if not isinstance(table_values, dict):
        table_values = row.get("tableValues")
    if not isinstance(table_values, dict):
        table_values = {}
    if pane_id == "oa":
        return text(
            table_values.get("applicationTime")
            or table_values.get("application_time")
            or row.get("application_time")
            or row.get("applicationTime")
            or row.get("date")
        )
    if pane_id == "bank":
        return text(
            table_values.get("transactionTime")
            or table_values.get("transaction_time")
            or row.get("transaction_time")
            or row.get("transactionTime")
            or row.get("trade_time")
            or row.get("tradeTime")
        )
    if pane_id == "invoice":
        return text(
            table_values.get("issueDate")
            or table_values.get("issue_date")
            or row.get("issue_date")
            or row.get("issueDate")
            or row.get("invoice_date")
            or row.get("invoiceDate")
        )
    return None


def _workbench_row_column_values(row: dict[str, Any], pane_id: str) -> dict[str, str]:
    table_values = row.get("table_values")
    if not isinstance(table_values, dict):
        table_values = row.get("tableValues")
    table_values = table_values if isinstance(table_values, dict) else {}
    if pane_id == "oa":
        return _clean_workbench_column_values(
            {
                "applicant": table_values.get("applicant") or row.get("applicant"),
                "projectName": table_values.get("projectName") or row.get("project_name_display") or row.get("project_name"),
                "applicationType": table_values.get("applicationType") or row.get("apply_type"),
                "counterparty": table_values.get("counterparty") or row.get("counterparty_name"),
                "reconciliationStatus": table_values.get("reconciliationStatus") or _workbench_relation_label(row),
                "amount": table_values.get("amount") or row.get("amount"),
                "reason": table_values.get("reason") or row.get("reason"),
            }
        )
    if pane_id == "bank":
        direction = text(table_values.get("direction")) or _workbench_bank_direction(row)
        payment_account = text(table_values.get("paymentAccount")) or text(row.get("payment_account_label"))
        return _clean_workbench_column_values(
            {
                "transactionTime": table_values.get("transactionTime") or row.get("trade_time"),
                "direction": direction,
                "amount": table_values.get("amount") or _workbench_bank_amount(row),
                "debitAmount": table_values.get("debitAmount") or row.get("debit_amount"),
                "creditAmount": table_values.get("creditAmount") or row.get("credit_amount"),
                "counterparty": table_values.get("counterparty") or row.get("counterparty_name"),
                "paymentAccount": payment_account,
                "invoiceRelationStatus": table_values.get("invoiceRelationStatus") or _workbench_relation_label(row),
                "paymentOrReceiptTime": table_values.get("paymentOrReceiptTime") or row.get("pay_receive_time"),
                "note": table_values.get("note") or row.get("remark"),
                "loanRepaymentDate": table_values.get("loanRepaymentDate") or row.get("repayment_date"),
            }
        )
    if pane_id == "invoice":
        return _clean_workbench_column_values(
            {
                "sellerTaxId": table_values.get("sellerTaxId") or row.get("seller_tax_no"),
                "sellerName": table_values.get("sellerName") or row.get("seller_name"),
                "buyerTaxId": table_values.get("buyerTaxId") or row.get("buyer_tax_no"),
                "buyerName": table_values.get("buyerName") or row.get("buyer_name"),
                "invoiceCode": table_values.get("invoiceCode") or row.get("invoice_code"),
                "invoiceNo": table_values.get("invoiceNo") or row.get("invoice_no") or row.get("digital_invoice_no"),
                "digitalInvoiceNo": table_values.get("digitalInvoiceNo") or row.get("digital_invoice_no"),
                "issueDate": table_values.get("issueDate") or row.get("issue_date"),
                "amount": table_values.get("amount") or row.get("amount"),
                "taxRate": table_values.get("taxRate") or row.get("tax_rate"),
                "taxAmount": table_values.get("taxAmount") or row.get("tax_amount"),
                "grossAmount": table_values.get("grossAmount") or row.get("total_with_tax"),
                "invoiceType": table_values.get("invoiceType") or row.get("invoice_type"),
            }
        )
    return {}


def _clean_workbench_column_values(values: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        normalized = text(value)
        if normalized is None or normalized in WORKBENCH_FILTER_PLACEHOLDERS:
            continue
        result[key] = normalized
    return result


def _workbench_bank_direction(row: dict[str, Any]) -> str | None:
    direction = text(row.get("direction"))
    if direction in {"支出", "收入"}:
        return direction
    if text(row.get("debit_amount")) not in {None, "", "--", "—"}:
        return "支出"
    if text(row.get("credit_amount")) not in {None, "", "--", "—"}:
        return "收入"
    return None


def _workbench_bank_amount(row: dict[str, Any]) -> str | None:
    return text(row.get("debit_amount")) or text(row.get("credit_amount")) or text(row.get("amount"))


def _workbench_relation_label(row: dict[str, Any]) -> str | None:
    for key in ("oa_bank_relation", "invoice_relation", "relation"):
        relation = row.get(key)
        if isinstance(relation, dict):
            label = text(relation.get("label"))
            if label:
                return label
    return text(row.get("status"))


def _workbench_date_from_text(value: str | None) -> str | None:
    normalized = text(value)
    if normalized is None:
        return None
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", normalized)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _searchable_row_text(row: dict[str, Any], pane_id: str) -> str:
    values = [text(row.get("id") or row.get("row_id")), text(row.get("label")), text(row.get("status"))]
    values.extend(text(value) for value in _workbench_row_column_values(row, pane_id).values())
    values.append(text(row.get("amount_value")))
    tags = row.get("tags")
    if isinstance(tags, list):
        values.extend(text(tag) for tag in tags)
    return " ".join(value for value in values if value)


def _workbench_group_row_identity(group: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    identities = []
    for fallback_row_type, row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
        if row_role == "summary":
            continue
        row_id = _workbench_row_id(row)
        if row_id is None:
            continue
        row_type = text(row.get("type") or row.get("record_type")) or fallback_row_type
        identities.append((row_type, row_id))
    return tuple(sorted(set(identities)))


def _workbench_group_row_records(group: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    group_id = text(group.get("group_id") or group.get("id"))
    zone = text(group.get("zone") or group.get("status")) or "open"
    if group_id is None:
        return records
    for pane, row_role, row_index, row in _iter_typed_group_rows_with_metadata(group):
        row_id = text(row.get("id") or row.get("row_id"))
        if row_id is None:
            continue
        column_values = _workbench_row_column_values(row, pane)
        time_value = _workbench_row_sort_value(row, pane)
        records.append(
            {
                "group_id": group_id,
                "zone": zone,
                "pane": pane,
                "row_id": row_id,
                "row_role": row_role,
                "row_index": row_index,
                "source_kind": text(row.get("source_kind") or row.get("type") or pane) or pane,
                "status": text(row.get("status") or zone) or zone,
                "time_value": time_value,
                "time_date": _workbench_date_from_text(time_value),
                "column_values": column_values,
                "searchable_text": _searchable_row_text(row, pane),
                "object_identity_key": text(row.get("object_identity_key")),
                "object_identity_kind": text(row.get("object_identity_kind")),
                "object_identity_source": text(row.get("object_identity_source")),
                "object_identity_confidence": text(row.get("object_identity_confidence")),
                "payload": serialize_value(row),
            }
        )
    return records


def _workbench_group_payload_for_rows(group: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(group.get("payload") if isinstance(group.get("payload"), dict) else group)
    payload.setdefault("group_id", text(group.get("group_id") or group.get("id")))
    payload.setdefault("zone", text(group.get("zone") or group.get("status")) or "open")
    payload.setdefault("status", text(group.get("status") or group.get("zone")) or "open")
    payload.setdefault("scope_month", group.get("scope_month"))
    payload.setdefault("month", group.get("month"))
    return payload


def _iter_typed_group_rows_with_metadata(group: dict[str, Any]) -> list[tuple[str, str, int, dict[str, Any]]]:
    rows: list[tuple[str, str, int, dict[str, Any]]] = []
    for row_type, key in (("oa", "oa_rows"), ("bank", "bank_rows"), ("invoice", "invoice_rows")):
        value = group.get(key)
        if isinstance(value, list):
            rows.extend(
                (
                    row_type,
                    "summary" if _is_workbench_summary_display_row(row, row_type) else "normal",
                    index,
                    row,
                )
                for index, row in enumerate(value)
                if isinstance(row, dict)
            )
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        for row_type, value in collapsed_rows.items():
            if isinstance(value, list):
                rows.extend((str(row_type), "collapsed", index, row) for index, row in enumerate(value) if isinstance(row, dict))
    return rows


def _iter_typed_group_rows(group: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for row_type, _row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
        rows.append((row_type, row))
    return rows


def _iter_group_rows(group: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in group.items():
        if str(key).endswith("_rows") and isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        for value in collapsed_rows.values():
            if isinstance(value, list):
                rows.extend(row for row in value if isinstance(row, dict))
    return rows


def _searchable_group_text(group: dict[str, Any]) -> str:
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for nested_value in value.values():
                collect(nested_value)
        elif isinstance(value, list):
            for nested_value in value:
                collect(nested_value)
        elif value not in (None, ""):
            values.append(str(value))

    collect(group)
    return " ".join(values)[:12000]


def _read_model_payload(row: dict[str, Any], *, drop_rebuildable_rows: bool = False) -> Any:
    payload = row_payload(row, "payload", "extra_payload", "raw_payload")
    if drop_rebuildable_rows and isinstance(payload, dict) and payload.get("rebuildable") is True:
        return None
    return without_keys(payload, {"rebuildable"})


def _workbench_reconciliation_row_types(payload: dict[str, Any]) -> list[str]:
    row_types: list[str] = []
    for row_type, key in (("oa", "oa_row_ids"), ("bank", "bank_row_ids"), ("invoice", "invoice_row_ids")):
        row_types.extend(row_type for _row_id in text_list(payload.get(key)))
    return row_types


def _workbench_reconciliation_decision_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    if isinstance(payload, dict) and payload:
        result = dict(payload)
    else:
        result = {}
    for key in (
        "decision_id",
        "decision_key",
        "display_state",
        "decision_status",
        "match_domain",
        "match_shape",
        "rule_code",
        "rule_version",
        "direction",
        "explanation",
    ):
        result[key] = text(row.get(key))
    result["scope_month"] = str(row.get("scope_month") or "")[:7]
    result["row_ids"] = text_list(row.get("row_ids"))
    result["oa_row_ids"] = text_list(row.get("oa_row_ids"))
    result["bank_row_ids"] = text_list(row.get("bank_row_ids"))
    result["invoice_row_ids"] = text_list(row.get("invoice_row_ids"))
    result["amount"] = decimal_text(row.get("amount"))
    result["payment_amount_closed"] = bool(row.get("payment_amount_closed"))
    result["invoice_amount_closed"] = bool(row.get("invoice_amount_closed"))
    result["warnings"] = row.get("warnings") if isinstance(row.get("warnings"), list) else []
    result["evidence"] = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    result["blockers"] = row.get("blockers") if isinstance(row.get("blockers"), list) else []
    result["source_versions"] = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
    result["consumed_by_relation_id"] = text(row.get("consumed_by_relation_id"))
    result["suppressed_by_exception_case_id"] = text(row.get("suppressed_by_exception_case_id"))
    return result


def _retry_backoff_case_sql(retry_backoff_seconds: list[int]) -> str:
    backoffs = [max(0, int_value(value, 0)) for value in retry_backoff_seconds]
    if not backoffs:
        backoffs = [0]
    clauses = " ".join(
        f"when attempt_count + 1 = {index} then {delay_seconds}"
        for index, delay_seconds in enumerate(backoffs, start=1)
    )
    return f"case {clauses} else {backoffs[-1]} end"


def _source_version_value(source_versions: Any) -> int | None:
    if not isinstance(source_versions, dict):
        return None
    value = source_versions.get("source_version")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _source_versions_from_scope_summary(scope_summary: dict[str, Any]) -> dict[str, Any]:
    signatures = scope_summary.get("scope_signatures") if isinstance(scope_summary.get("scope_signatures"), dict) else {}
    scope_keys = text_list(scope_summary.get("scope_keys"))
    if len(scope_keys) == 1:
        signature = signatures.get(scope_keys[0]) if isinstance(signatures.get(scope_keys[0]), dict) else {}
        source_versions = signature.get("source_versions") if isinstance(signature.get("source_versions"), dict) else {}
        return dict(source_versions)
    result: dict[str, Any] = {}
    for scope_key in scope_keys:
        signature = signatures.get(scope_key) if isinstance(signatures.get(scope_key), dict) else {}
        if isinstance(signature.get("source_versions"), dict):
            result[scope_key] = dict(signature.get("source_versions"))
    return result


def _scope_source_versions_by_month(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_rows = [row for row in list(rows or []) if isinstance(row, dict)]
    if not normalized_rows:
        return {}
    if len(normalized_rows) == 1:
        source_versions = normalized_rows[0].get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}
    result: dict[str, Any] = {}
    for row in normalized_rows:
        scope_key = text(row.get("scope_key"))
        source_versions = row.get("source_versions")
        if scope_key and isinstance(source_versions, dict):
            result[scope_key] = dict(source_versions)
    return result


def _workbench_relation_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    base = dict(payload) if isinstance(payload, dict) else {}
    row_id = text(base.get("row_id") or row.get("row_id")) or ""
    row_type = text(base.get("row_type") or row.get("row_type")) or ""
    relation_status = text(base.get("relation_status") or row.get("relation_status")) or "unlinked"
    return {
        "row_id": row_id,
        "row_type": row_type,
        "scope_key": text(base.get("scope_key") or row.get("scope_key")),
        "scope_month": text(base.get("scope_month") or row.get("scope_month")),
        "relation_status": relation_status,
        "group_ids": text_list(base.get("group_ids") if "group_ids" in base else row.get("group_ids")),
        "linked_oa": _list_payload(base.get("linked_oa") if "linked_oa" in base else row.get("linked_oa")),
        "linked_bank_transactions": _list_payload(
            base.get("linked_bank_transactions")
            if "linked_bank_transactions" in base
            else row.get("linked_bank_transactions")
        ),
        "linked_input_invoices": _list_payload(
            base.get("linked_input_invoices") if "linked_input_invoices" in base else row.get("linked_input_invoices")
        ),
        "linked_output_invoices": _list_payload(
            base.get("linked_output_invoices")
            if "linked_output_invoices" in base
            else row.get("linked_output_invoices")
        ),
        "payload": base.get("payload") if isinstance(base.get("payload"), dict) else {},
    }


def _workbench_relation_group_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    base = dict(payload) if isinstance(payload, dict) else {}
    relation_payload = base.get("payload") if isinstance(base.get("payload"), dict) else base
    return {
        "group_id": text(base.get("group_id") or row.get("group_id")) or "",
        "scope_key": text(base.get("scope_key") or row.get("scope_key")),
        "scope_month": text(base.get("scope_month") or row.get("scope_month")),
        "relation_source": text(base.get("relation_source") or row.get("relation_source")) or "manual",
        "relation_kind": text(base.get("relation_kind") or row.get("relation_kind")) or "linked",
        "relation_status": text(base.get("relation_status") or row.get("relation_status")) or "linked",
        "oa_row_ids": text_list(base.get("oa_row_ids") if "oa_row_ids" in base else row.get("oa_row_ids")),
        "bank_transaction_ids": text_list(
            base.get("bank_transaction_ids") if "bank_transaction_ids" in base else row.get("bank_transaction_ids")
        ),
        "input_invoice_ids": text_list(
            base.get("input_invoice_ids") if "input_invoice_ids" in base else row.get("input_invoice_ids")
        ),
        "output_invoice_ids": text_list(
            base.get("output_invoice_ids") if "output_invoice_ids" in base else row.get("output_invoice_ids")
        ),
        "payload": relation_payload,
    }


def _source_versions_from_relation_records(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in list(rows or []):
        if isinstance(row, dict) and isinstance(row.get("source_versions"), dict):
            return dict(row.get("source_versions"))
        payload = _read_model_payload(row) if isinstance(row, dict) else {}
        if isinstance(payload, dict) and isinstance(payload.get("source_versions"), dict):
            return dict(payload.get("source_versions"))
    return {}


def _list_payload(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def _dedupe_preserve_order(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text_value = text(value)
        if text_value is None or text_value in seen:
            continue
        seen.add(text_value)
        result.append(text_value)
    return result
