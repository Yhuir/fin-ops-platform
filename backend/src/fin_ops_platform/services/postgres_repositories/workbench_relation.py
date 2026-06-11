from __future__ import annotations

from typing import Any

from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService
from fin_ops_platform.services.postgres_repositories.common import (
    event_uuid,
    int_value,
    iter_mapping,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    text,
    text_list,
)
from fin_ops_platform.services.postgres_snapshot_contracts import normalize_workbench_pair_relations


class PostgresWorkbenchRelationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select case_id as key, raw_payload from app.workbench_pair_relations order by case_id")
        if not rows:
            return {}
        history_rows = self._connection.fetch_all(
            """
            select raw_payload
            from app.workbench_pair_relation_history
            order by
                (raw_payload->'raw_payload'->>'_stage04_child_index')::integer nulls last,
                occurred_at,
                case_id
            """
        )
        return normalize_workbench_pair_relations(
            {str(row.get("key")): row_payload(row, "raw_payload") for row in rows},
            [payload for row in history_rows if isinstance((payload := row_payload(row, "raw_payload")), dict)],
        )

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: set[str] | None = None,
    ) -> None:
        def write(connection: Any) -> None:
            relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else None
            changed_ids = {str(item) for item in changed_case_ids} if changed_case_ids is not None else None
            dirty_scope_keys: set[str] = set()
            for case_id, payload in iter_mapping(relations):
                if changed_ids is not None and case_id not in changed_ids:
                    continue
                dirty_scope_keys.update(_workbench_relation_dirty_scope_keys(connection, payload))
                connection.execute(
                    """
                    insert into app.workbench_pair_relations(
                        case_id, relation_mode, status, version, month_scope, row_ids, row_types,
                        note, amount_check, special_metadata, source_versions, raw_payload
                    )
                    values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (case_id) do update set
                        relation_mode = excluded.relation_mode,
                        status = excluded.status,
                        version = excluded.version,
                        month_scope = excluded.month_scope,
                        row_ids = excluded.row_ids,
                        row_types = excluded.row_types,
                        note = excluded.note,
                        amount_check = excluded.amount_check,
                        special_metadata = excluded.special_metadata,
                        source_versions = excluded.source_versions,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        case_id,
                        text(payload.get("relation_mode") or payload.get("mode") or "unknown"),
                        text(payload.get("status") or "active"),
                        int_value(payload.get("version"), 1),
                        month_start(payload.get("month_scope") or payload.get("scope_month") or payload.get("month")),
                        text_list(payload.get("row_ids")),
                        text_list(payload.get("row_types")),
                        text(payload.get("note")),
                        jsonb(payload.get("amount_check") if isinstance(payload.get("amount_check"), dict) else {}),
                        jsonb(payload.get("special_metadata") if isinstance(payload.get("special_metadata"), dict) else {}),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            history = snapshot.get("pair_relation_history") if isinstance(snapshot, dict) else None
            self._replace_workbench_pair_relation_history(connection, history, changed_case_ids=changed_ids)
            for scope_key in sorted(dirty_scope_keys or {"all"}):
                _enqueue_read_model_refresh_in_transaction(
                    connection,
                    scope_type="workbench_relation",
                    scope_key=scope_key,
                    reason="workbench_pair_relation_changed",
                )
                for downstream_scope_type in (
                    "bank_detail",
                    "input_invoice_usage",
                    "output_invoice_collection",
                    "oa_pending_payment",
                    "search",
                    "cost_statistics",
                    "tax_offset",
                    "no_oa_bank_batch",
                ):
                    _enqueue_read_model_refresh_in_transaction(
                        connection,
                        scope_type=downstream_scope_type,
                        scope_key=scope_key,
                        reason="workbench_relation_changed",
                    )
            if dirty_scope_keys:
                for pending_scope_key in (
                    "expense:all",
                    "expense:requires_invoice",
                    "expense:bank_statement_as_invoice",
                    "expense:no_invoice_required",
                    "income:all",
                    "income:requires_invoice",
                    "income:no_invoice_required",
                    "income:cash_income",
                ):
                    _enqueue_read_model_refresh_in_transaction(
                        connection,
                        scope_type="pending_invoice",
                        scope_key=pending_scope_key,
                        reason="workbench_relation_changed",
                    )

        run_in_transaction(self._connection, write)

    def _replace_workbench_pair_relation_history(self, connection: Any, history: Any, *, changed_case_ids: set[str] | None) -> None:
        if not isinstance(history, list):
            return
        case_ids = {
            normalized
            for item in history
            if isinstance(item, dict)
            for normalized in self._history_case_ids(item)
        }
        if changed_case_ids is not None:
            case_ids &= changed_case_ids
        for case_id in sorted(case_ids):
            connection.execute("delete from app.workbench_pair_relation_history where case_id = %s", (case_id,))
        for item in history:
            if not isinstance(item, dict):
                continue
            item_case_ids = self._history_case_ids(item)
            if changed_case_ids is not None and not (set(item_case_ids) & changed_case_ids):
                continue
            for case_id in item_case_ids:
                connection.execute(
                    """
                    insert into app.workbench_pair_relation_history(
                        id, relation_id, case_id, event_type, actor_id, occurred_at,
                        before_payload, after_payload, raw_payload
                    )
                    values (
                        %s::uuid,
                        (select id from app.workbench_pair_relations where case_id = %s limit 1),
                        %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s
                    )
                    on conflict (id) do update set
                        before_payload = excluded.before_payload,
                        after_payload = excluded.after_payload,
                        raw_payload = excluded.raw_payload
                    """,
                    (
                        event_uuid("workbench_pair_relation_history", case_id, item),
                        case_id,
                        case_id,
                        text(item.get("operation_type") or item.get("event_type") or "unknown"),
                        text(item.get("created_by") or item.get("actor_id")),
                        text(item.get("created_at") or item.get("occurred_at")),
                        jsonb(item.get("before_relations") if isinstance(item.get("before_relations"), list) else item.get("before_payload") or {}),
                        jsonb(item.get("after_relations") if isinstance(item.get("after_relations"), list) else item.get("after_payload") or {}),
                        jsonb({"normalized_payload": item}),
                    ),
                )

    @staticmethod
    def _history_case_ids(item: dict[str, Any]) -> list[str]:
        case_ids: list[str] = []
        for key in ("case_id", "relation_case_id"):
            if normalized := text(item.get(key)):
                case_ids.append(normalized)
        for collection_key in ("after_relations", "before_relations"):
            relations = item.get(collection_key)
            if isinstance(relations, list):
                for relation in relations:
                    if isinstance(relation, dict) and (normalized := text(relation.get("case_id"))):
                        case_ids.append(normalized)
        return sorted(set(case_ids))


def _workbench_relation_dirty_scope_keys(connection: Any, relation: dict[str, Any]) -> set[str]:
    scope_keys: set[str] = set()
    scope_month = month_start(relation.get("month_scope") or relation.get("scope_month") or relation.get("month"))
    if scope_month is not None:
        scope_keys.add(str(scope_month)[:7])
    row_ids = text_list(relation.get("row_ids"))
    if row_ids:
        rows = connection.fetch_all(
            """
            select distinct scope_key
            from (
                select to_char(txn_month, 'YYYY-MM') as scope_key
                from app.bank_transactions
                where txn_month is not null
                  and coalesce(legacy_mongo_id, id::text) = any(%s)
                union
                select to_char(invoice_month, 'YYYY-MM') as scope_key
                from app.invoices
                where invoice_month is not null
                  and coalesce(legacy_mongo_id, id::text) = any(%s)
                union
                select to_char(date_trunc('month', application_date)::date, 'YYYY-MM') as scope_key
                from app.oa_applications
                where application_date is not null
                  and row_id = any(%s)
                union
                select to_char(scope_month, 'YYYY-MM') as scope_key
                from read_model.workbench_rows
                where scope_month is not null
                  and row_id = any(%s)
            ) scopes
            where scope_key is not null
            order by scope_key
            """,
            (row_ids, row_ids, row_ids, row_ids),
        )
        scope_keys.update(text(row.get("scope_key")) for row in rows if text(row.get("scope_key")))
    return scope_keys or {"all"}


def _enqueue_read_model_refresh_in_transaction(
    connection: Any,
    *,
    scope_type: str,
    scope_key: str,
    reason: str,
    tenant_id: str = "default",
) -> None:
    if scope_type == "cost_statistics":
        for target_scope_key in CostStatisticsRuntimeService.refresh_scope_keys_from_scope_keys([scope_key]):
            _enqueue_single_read_model_refresh_in_transaction(
                connection,
                scope_type=scope_type,
                scope_key=target_scope_key,
                reason=reason,
                tenant_id=tenant_id,
            )
        return
    _enqueue_single_read_model_refresh_in_transaction(
        connection,
        scope_type=scope_type,
        scope_key=scope_key,
        reason=reason,
        tenant_id=tenant_id,
    )


def _enqueue_single_read_model_refresh_in_transaction(
    connection: Any,
    *,
    scope_type: str,
    scope_key: str,
    reason: str,
    tenant_id: str = "default",
) -> None:
    payload = {
        "scope_type": scope_type,
        "scope_key": scope_key,
        "reason": reason,
    }
    dirty_row = connection.fetch_one(
        """
        insert into job.read_model_dirty_scopes(
            tenant_id, scope_type, scope_key, reason, payload, raw_payload,
            source_version, status, next_run_at, priority
        )
        values (
            %s, %s, %s, %s, %s, %s,
            coalesce((
                select max(existing.source_version) + 1
                from job.read_model_dirty_scopes existing
                where existing.tenant_id = %s
                  and existing.scope_type = %s
                  and existing.scope_key = %s
            ), 0),
            'pending',
            now(),
            'normal'
        )
        on conflict (tenant_id, scope_type, scope_key)
        where status in ('pending', 'processing')
        do update set
            reason = excluded.reason,
            payload = job.read_model_dirty_scopes.payload || excluded.payload,
            raw_payload = excluded.raw_payload,
            source_version = job.read_model_dirty_scopes.source_version + 1,
            status = 'pending',
            next_run_at = now(),
            priority = excluded.priority,
            updated_at = now()
        returning source_version
        """,
        (
            tenant_id,
            scope_type,
            scope_key,
            reason,
            jsonb(payload),
            jsonb(payload),
            tenant_id,
            scope_type,
            scope_key,
        ),
    )
    source_version = int_value((dirty_row or {}).get("source_version"), 0)
    event_type = f"{scope_type}.read_model.refresh"
    event_payload = {**payload, "source_version": source_version}
    connection.execute(
        """
        insert into job.outbox_events (
            tenant_id, event_type, aggregate_type, aggregate_id,
            scope_type, scope_key, dedupe_key, schema_version,
            source_version, priority, payload, raw_payload
        )
        values (%s, %s, 'read_model', %s, %s, %s, %s, 1, %s, 'normal', %s, %s)
        on conflict (tenant_id, dedupe_key)
        where dedupe_key is not null and status = 'pending'
        do update set
            payload = job.outbox_events.payload || excluded.payload,
            raw_payload = excluded.raw_payload,
            source_version = excluded.source_version,
            priority = excluded.priority,
            publish_status = 'unpublished',
            published_at = null,
            publish_last_error = null,
            next_publish_at = now(),
            publish_locked_by = null,
            publish_locked_at = null,
            publish_confirmed_at = null,
            updated_at = now()
        """,
        (
            tenant_id,
            event_type,
            scope_key,
            scope_type,
            scope_key,
            f"{event_type}:{scope_type}:{scope_key}",
            source_version,
            jsonb(event_payload),
            jsonb(event_payload),
        ),
    )
