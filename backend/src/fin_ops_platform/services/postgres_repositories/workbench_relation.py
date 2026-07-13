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
from fin_ops_platform.services.postgres_repositories.oa_projection import COMPLETED_WORKFLOW_STATUS_SQL
from fin_ops_platform.services.postgres_snapshot_contracts import normalize_workbench_pair_relations


WORKBENCH_RELATION_DOWNSTREAM_SCOPE_TYPES = (
    "bank_detail",
    "invoice_lifecycle",
    "input_invoice_usage",
    "output_invoice_collection",
    "oa_pending_payment",
    "search",
    "cost_statistics",
    "no_oa_bank_batch",
    "bank_flow_rule_batch",
)

NO_OA_BANK_BATCH_RELATION_MODE = "no_oa_bank_batch"
BANK_FLOW_RULE_BATCH_RELATION_MODE = "bank_flow_rule_batch"
_NO_OA_RELATION_MODES = frozenset({NO_OA_BANK_BATCH_RELATION_MODE})
_NO_OA_BATCH_READ_MODEL_RELATION_MODES = frozenset(
    {
        NO_OA_BANK_BATCH_RELATION_MODE,
    }
)
_EXPENSE_PENDING_INVOICE_SCOPE_KEYS = (
    "expense:all",
    "expense:requires_invoice",
    "expense:bank_statement_as_invoice",
    "expense:no_invoice_required",
)
_INCOME_PENDING_INVOICE_SCOPE_KEYS = (
    "income:all",
    "income:requires_invoice",
    "income:no_invoice_required",
    "income:cash_income",
)


class PostgresWorkbenchRelationRepository:
    def __init__(self, connection: Any, *, enqueue_refreshes: bool = True) -> None:
        self._connection = connection
        self._enqueue_refreshes = bool(enqueue_refreshes)

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

    def load_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_row_ids = text_list(row_ids)
        normalized_case_ids = text_list(case_ids)
        predicates: list[str] = []
        params: list[Any] = []
        if normalized_row_ids:
            predicates.append("row_ids && %s::text[]")
            params.append(normalized_row_ids)
        if normalized_case_ids:
            predicates.append("case_id = any(%s::text[])")
            params.append(normalized_case_ids)
        if not predicates:
            return {}

        rows = self._connection.fetch_all(
            f"""
            select case_id as key, raw_payload
            from app.workbench_pair_relations
            where {' or '.join(predicates)}
            order by case_id
            """,
            tuple(params),
        )
        if not rows:
            return {}

        relations = {
            str(row.get("key")): row_payload(row, "raw_payload")
            for row in rows
        }
        selected_case_ids = text_list(list(relations))
        history_rows = self._connection.fetch_all(
            """
            select raw_payload
            from app.workbench_pair_relation_history
            where case_id = any(%s::text[])
            order by
                (raw_payload->'raw_payload'->>'_stage04_child_index')::integer nulls last,
                occurred_at,
                case_id
            """,
            (selected_case_ids,),
        )
        return normalize_workbench_pair_relations(
            relations,
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
            downstream_by_scope_key: dict[str, set[str]] = {}
            no_oa_batch_relation_modes_by_scope: dict[str, set[str]] = {}
            bank_flow_batch_relation_modes_by_scope: dict[str, set[str]] = {}
            pending_invoice_scope_keys: set[str] = set()
            refresh_row_ids: set[str] = set()
            refresh_case_ids: set[str] = set()
            for case_id, payload in iter_mapping(relations):
                if changed_ids is not None and case_id not in changed_ids:
                    continue
                if self._enqueue_refreshes:
                    normalized_case_id = text(case_id) or text(payload.get("case_id"))
                    if normalized_case_id:
                        refresh_case_ids.add(normalized_case_id)
                    refresh_row_ids.update(text_list(payload.get("row_ids")))
                    relation_mode = text(payload.get("relation_mode") or payload.get("mode"))
                    domain_scope_keys = _workbench_relation_domain_scope_keys(connection, payload)
                    relation_scope_keys = _workbench_relation_dirty_scope_keys_from_domain_scope_keys(domain_scope_keys)
                    dirty_scope_keys.update(relation_scope_keys)
                    scope_map = _workbench_relation_downstream_scope_map(
                        connection,
                        payload,
                        domain_scope_keys=domain_scope_keys,
                        dirty_scope_keys=relation_scope_keys,
                    )
                    for scope_key, downstream_scope_types in scope_map.items():
                        downstream_by_scope_key.setdefault(scope_key, set()).update(downstream_scope_types)
                        if (
                            relation_mode in _NO_OA_BATCH_READ_MODEL_RELATION_MODES
                            and "no_oa_bank_batch" in downstream_scope_types
                        ):
                            no_oa_batch_relation_modes_by_scope.setdefault(scope_key, set()).add(relation_mode)
                        if (
                            relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE
                            and "bank_flow_rule_batch" in downstream_scope_types
                        ):
                            bank_flow_batch_relation_modes_by_scope.setdefault(scope_key, set()).add(relation_mode)
                    pending_invoice_scope_keys.update(
                        _workbench_relation_pending_invoice_scope_keys(
                            connection,
                            payload,
                            domain_scope_keys=domain_scope_keys,
                        )
                    )
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
            if not self._enqueue_refreshes:
                return
            refresh_metadata: dict[str, Any] = {}
            if refresh_row_ids:
                refresh_metadata["row_ids"] = sorted(refresh_row_ids)
            if refresh_case_ids:
                refresh_metadata["case_ids"] = sorted(refresh_case_ids)
            refreshes: list[dict[str, Any]] = []
            relation_refresh_scope_keys = set(dirty_scope_keys or {"all"})
            downstream_refresh_scope_keys = relation_refresh_scope_keys | set(downstream_by_scope_key.keys())
            for scope_key in sorted(downstream_refresh_scope_keys or {"all"}):
                if scope_key in relation_refresh_scope_keys:
                    _append_read_model_refresh(
                        refreshes,
                        scope_type="workbench_relation",
                        scope_key=scope_key,
                        reason="workbench_pair_relation_changed",
                        priority="high",
                        metadata=refresh_metadata,
                    )
                downstream_scope_types = downstream_by_scope_key.get(scope_key, set())
                for downstream_scope_type in WORKBENCH_RELATION_DOWNSTREAM_SCOPE_TYPES:
                    if downstream_scope_type not in downstream_scope_types:
                        continue
                    if downstream_scope_type == "no_oa_bank_batch":
                        relation_modes = sorted(no_oa_batch_relation_modes_by_scope.get(scope_key) or [])
                        if relation_modes:
                            for relation_mode in relation_modes:
                                _append_read_model_refresh(
                                    refreshes,
                                    scope_type=downstream_scope_type,
                                    scope_key=scope_key,
                                    reason="workbench_relation_changed",
                                    priority="high",
                                    payload_extra={"relation_mode": relation_mode},
                                    dedupe_kind=relation_mode,
                                    metadata=refresh_metadata,
                                )
                            continue
                    if downstream_scope_type == "bank_flow_rule_batch":
                        relation_modes = sorted(bank_flow_batch_relation_modes_by_scope.get(scope_key) or [])
                        if relation_modes:
                            for relation_mode in relation_modes:
                                _append_read_model_refresh(
                                    refreshes,
                                    scope_type=downstream_scope_type,
                                    scope_key=scope_key,
                                    reason="workbench_relation_changed",
                                    priority="high",
                                    payload_extra={"relation_mode": relation_mode},
                                    dedupe_kind=relation_mode,
                                    metadata=refresh_metadata,
                                )
                            continue
                    _append_read_model_refresh(
                        refreshes,
                        scope_type=downstream_scope_type,
                        scope_key=scope_key,
                        reason="workbench_relation_changed",
                        priority="high",
                        metadata=refresh_metadata,
                    )
            workbench_scope_keys = _workbench_relation_workbench_refresh_scope_keys(dirty_scope_keys)
            workbench_month_scope_keys = sorted(scope_key for scope_key in workbench_scope_keys if scope_key != "all")
            for scope_key in workbench_month_scope_keys:
                _append_read_model_refresh(
                    refreshes,
                    scope_type="workbench",
                    scope_key=scope_key,
                    reason="workbench_relation_changed",
                    priority="high",
                    metadata=refresh_metadata,
                )
            if "all" in workbench_scope_keys:
                if workbench_month_scope_keys:
                    _append_read_model_refresh(
                        refreshes,
                        scope_type="workbench",
                        scope_key="all",
                        reason="workbench_relation_changed",
                        priority="high",
                        payload_extra={
                            "aggregate_only": True,
                            "parent_scope_keys": workbench_month_scope_keys,
                        },
                        dedupe_kind="aggregate",
                        metadata=refresh_metadata,
                    )
                else:
                    _append_read_model_refresh(
                        refreshes,
                        scope_type="workbench",
                        scope_key="all",
                        reason="workbench_relation_changed",
                        priority="high",
                        metadata=refresh_metadata,
                    )
            if dirty_scope_keys and pending_invoice_scope_keys:
                for pending_scope_key in sorted(pending_invoice_scope_keys):
                    _append_read_model_refresh(
                        refreshes,
                        scope_type="pending_invoice",
                        scope_key=pending_scope_key,
                        reason="workbench_relation_changed",
                        priority="high",
                        metadata=refresh_metadata,
                    )
            _enqueue_read_model_refreshes_in_transaction(connection, refreshes)

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
    return _workbench_relation_dirty_scope_keys_from_domain_scope_keys(
        _workbench_relation_domain_scope_keys(connection, relation)
    )


def _workbench_relation_downstream_scope_types(connection: Any, relation: dict[str, Any]) -> set[str]:
    downstream_scope_types: set[str] = set()
    for scope_types in _workbench_relation_downstream_scope_map(connection, relation).values():
        downstream_scope_types.update(scope_types)
    return downstream_scope_types


def _workbench_relation_downstream_scope_map(
    connection: Any,
    relation: dict[str, Any],
    *,
    domain_scope_keys: dict[str, set[str]] | None = None,
    dirty_scope_keys: set[str] | None = None,
) -> dict[str, set[str]]:
    row_ids = text_list(relation.get("row_ids"))
    row_types = {item for item in text_list(relation.get("row_types")) if item}
    relation_mode = text(relation.get("relation_mode") or relation.get("mode"))
    domain_scope_keys = domain_scope_keys or _workbench_relation_domain_scope_keys(connection, relation)
    dirty_scope_keys = dirty_scope_keys or _workbench_relation_dirty_scope_keys_from_domain_scope_keys(domain_scope_keys)

    unknown_row_types = not row_types
    has_bank = "bank" in row_types or unknown_row_types
    has_invoice = "invoice" in row_types or unknown_row_types
    has_oa = "oa" in row_types
    is_no_oa_batch = relation_mode in _NO_OA_RELATION_MODES
    is_bank_flow_rule_batch = relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE
    actual_invoice_scope_keys = set(domain_scope_keys.get("invoice", set()))
    actual_oa_scope_keys = set(domain_scope_keys.get("oa", set()))
    bank_scope_keys = _domain_scope_keys(domain_scope_keys, "bank", dirty_scope_keys)
    invoice_scope_keys = _domain_scope_keys(domain_scope_keys, "invoice", dirty_scope_keys)
    oa_scope_keys = _domain_scope_keys(domain_scope_keys, "oa", dirty_scope_keys)
    broad_scope_keys = set(dirty_scope_keys or {"all"})
    scope_map: dict[str, set[str]] = {}

    def add(scope_type: str, scope_keys: set[str]) -> None:
        for scope_key in sorted(scope_keys or {"all"}):
            scope_map.setdefault(scope_key, set()).add(scope_type)

    add("search", broad_scope_keys)
    if has_bank:
        add("bank_detail", broad_scope_keys if unknown_row_types else bank_scope_keys)
    if has_invoice or has_oa or unknown_row_types:
        lifecycle_scope_keys: set[str] = set()
        if has_invoice:
            lifecycle_scope_keys.update(broad_scope_keys if unknown_row_types else invoice_scope_keys)
        if has_oa:
            lifecycle_scope_keys.update(oa_scope_keys)
        add("invoice_lifecycle", lifecycle_scope_keys or broad_scope_keys)
    if has_invoice or unknown_row_types:
        invoice_downstream_scope_keys = broad_scope_keys if unknown_row_types else (actual_invoice_scope_keys or {"all"})
        add("input_invoice_usage", invoice_downstream_scope_keys)
        add("output_invoice_collection", invoice_downstream_scope_keys)
    if has_bank or has_invoice or has_oa or unknown_row_types:
        add("oa_pending_payment", actual_oa_scope_keys or broad_scope_keys)
    cost_scope_keys: set[str] = set()
    if unknown_row_types:
        cost_scope_keys = broad_scope_keys
    elif has_bank and (has_oa or is_no_oa_batch or is_bank_flow_rule_batch or relation_mode == "turnover_manual_closure"):
        cost_scope_keys = bank_scope_keys
    if cost_scope_keys:
        add("cost_statistics", cost_scope_keys)
    if relation_mode in _NO_OA_BATCH_READ_MODEL_RELATION_MODES:
        add("no_oa_bank_batch", bank_scope_keys)
    if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE:
        add("bank_flow_rule_batch", bank_scope_keys)
    return scope_map


def _workbench_relation_pending_invoice_scope_keys(
    connection: Any,
    relation: dict[str, Any],
    *,
    domain_scope_keys: dict[str, set[str]] | None = None,
) -> set[str]:
    row_types = {item for item in text_list(relation.get("row_types")) if item}
    if row_types and "bank" not in row_types:
        return set()
    domain_scope_keys = domain_scope_keys or _workbench_relation_domain_scope_keys(connection, relation)
    directions = _workbench_relation_bank_directions(connection, text_list(relation.get("row_ids")))
    if not directions:
        directions = {"expense", "income"}
    base_scope_keys: set[str] = set()
    if "expense" in directions:
        base_scope_keys.update(_EXPENSE_PENDING_INVOICE_SCOPE_KEYS)
    if "income" in directions:
        base_scope_keys.update(_INCOME_PENDING_INVOICE_SCOPE_KEYS)
    return _month_scoped_pending_invoice_scope_keys(
        base_scope_keys,
        domain_scope_keys.get("bank", set())
        or domain_scope_keys.get("relation", set())
        or domain_scope_keys.get("workbench", set()),
    )


def _workbench_relation_domain_scope_keys(connection: Any, relation: dict[str, Any]) -> dict[str, set[str]]:
    row_types = {item for item in text_list(relation.get("row_types")) if item}
    relation_mode = text(relation.get("relation_mode") or relation.get("mode"))
    relation_scope_keys = _relation_month_scope_keys(relation)
    unknown_row_types = not row_types
    has_bank = "bank" in row_types or unknown_row_types
    has_invoice = "invoice" in row_types or unknown_row_types
    has_oa = "oa" in row_types or unknown_row_types
    can_use_relation_month_for_bank = (
        bool(relation_scope_keys)
        and has_bank
        and not has_invoice
        and not has_oa
        and relation_mode in {*_NO_OA_BATCH_READ_MODEL_RELATION_MODES, BANK_FLOW_RULE_BATCH_RELATION_MODE}
    )
    bank_scope_keys = (
        set(relation_scope_keys)
        if can_use_relation_month_for_bank
        else _workbench_relation_bank_scope_keys(connection, relation)
        if has_bank
        else set()
    )
    invoice_scope_keys = _workbench_relation_invoice_scope_keys(connection, relation) if has_invoice else set()
    oa_scope_keys = _workbench_relation_oa_scope_keys(connection, relation) if has_oa else set()
    workbench_scope_keys = (
        set()
        if relation_scope_keys or bank_scope_keys or invoice_scope_keys or oa_scope_keys
        else _workbench_relation_workbench_scope_keys(connection, relation)
    )
    return {
        "relation": relation_scope_keys,
        "bank": bank_scope_keys,
        "invoice": invoice_scope_keys,
        "oa": oa_scope_keys,
        "workbench": workbench_scope_keys,
    }


def _workbench_relation_dirty_scope_keys_from_domain_scope_keys(domain_scope_keys: dict[str, set[str]]) -> set[str]:
    scope_keys: set[str] = set()
    for key in ("relation", "bank", "invoice", "oa", "workbench"):
        scope_keys.update(domain_scope_keys.get(key, set()))
    return scope_keys or {"all"}


def _workbench_relation_workbench_refresh_scope_keys(scope_keys: set[str]) -> set[str]:
    normalized_scope_keys = {
        str(scope_key).strip()
        for scope_key in set(scope_keys or set())
        if str(scope_key).strip()
    }
    if not normalized_scope_keys:
        return {"all"}
    if normalized_scope_keys == {"all"}:
        return {"all"}
    return set(normalized_scope_keys)


def _domain_scope_keys(domain_scope_keys: dict[str, set[str]], key: str, dirty_scope_keys: set[str]) -> set[str]:
    scope_keys = set(domain_scope_keys.get(key, set()))
    if scope_keys:
        return scope_keys
    relation_scope_keys = set(domain_scope_keys.get("relation", set()))
    if relation_scope_keys:
        return relation_scope_keys
    return set(dirty_scope_keys or {"all"})


def _relation_month_scope_keys(relation: dict[str, Any]) -> set[str]:
    scope_month = month_start(relation.get("month_scope") or relation.get("scope_month") or relation.get("month"))
    return {str(scope_month)[:7]} if scope_month is not None else set()


def _month_scoped_pending_invoice_scope_keys(base_scope_keys: set[str], month_scope_keys: set[str]) -> set[str]:
    months = sorted(
        {
            str(scope_key).strip()[:7]
            for scope_key in month_scope_keys
            if len(str(scope_key).strip()) >= 7
            and str(scope_key).strip()[4] == "-"
            and str(scope_key).strip()[5:7].isdigit()
        }
    )
    if not months:
        return set(base_scope_keys)
    return {f"{scope_key}:{month}" for scope_key in base_scope_keys for month in months}


def _workbench_relation_bank_scope_keys(connection: Any, relation: dict[str, Any]) -> set[str]:
    row_ids = text_list(relation.get("row_ids"))
    if not row_ids:
        return set()
    rows = connection.fetch_all(
        """
        select distinct to_char(txn_month, 'YYYY-MM') as scope_key
        from app.bank_transactions
        where status <> 'deleted'
          and txn_month is not null
          and coalesce(legacy_mongo_id, id::text) = any(%s)
        order by scope_key
        """,
        (row_ids,),
    )
    return {text(row.get("scope_key")) for row in rows if text(row.get("scope_key"))}


def _workbench_relation_invoice_scope_keys(connection: Any, relation: dict[str, Any]) -> set[str]:
    row_ids = text_list(relation.get("row_ids"))
    if not row_ids:
        return set()
    rows = connection.fetch_all(
        """
        select distinct to_char(invoice_month, 'YYYY-MM') as scope_key
        from app.invoices
        where status <> 'deleted'
          and invoice_month is not null
          and coalesce(legacy_mongo_id, id::text) = any(%s)
        order by scope_key
        """,
        (row_ids,),
    )
    return {text(row.get("scope_key")) for row in rows if text(row.get("scope_key"))}


def _workbench_relation_oa_scope_keys(connection: Any, relation: dict[str, Any]) -> set[str]:
    row_ids = text_list(relation.get("row_ids"))
    if not row_ids:
        return set()
    rows = connection.fetch_all(
        """
        select distinct to_char(date_trunc('month', application_date)::date, 'YYYY-MM') as scope_key
        from app.oa_applications
        where application_date is not null
          and row_id = any(%s)
          and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
        order by scope_key
        """,
        (row_ids,),
    )
    return {text(row.get("scope_key")) for row in rows if text(row.get("scope_key"))}


def _workbench_relation_workbench_scope_keys(connection: Any, relation: dict[str, Any]) -> set[str]:
    row_ids = text_list(relation.get("row_ids"))
    if not row_ids:
        return set()
    rows = connection.fetch_all(
        """
        select distinct to_char(scope_month, 'YYYY-MM') as scope_key
        from read_model.workbench_rows
        where scope_month is not null
          and row_id = any(%s)
        order by scope_key
        """,
        (row_ids,),
    )
    return {text(row.get("scope_key")) for row in rows if text(row.get("scope_key"))}


def _workbench_relation_bank_directions(connection: Any, row_ids: list[str]) -> set[str]:
    if not row_ids:
        return set()
    rows = connection.fetch_all(
        """
        select distinct txn_direction
        from app.bank_transactions
        where status <> 'deleted'
          and coalesce(legacy_mongo_id, id::text) = any(%s)
        """,
        (row_ids,),
    )
    directions: set[str] = set()
    for row in rows:
        txn_direction = (text(row.get("txn_direction")) or "").lower()
        if txn_direction in {"outflow", "debit", "expense"} or "支" in txn_direction or "付" in txn_direction:
            directions.add("expense")
        if txn_direction in {"inflow", "credit", "income"} or "收" in txn_direction or "入" in txn_direction:
            directions.add("income")
    return directions


def _append_read_model_refresh(
    refreshes: list[dict[str, Any]],
    *,
    scope_type: str,
    scope_key: str,
    reason: str,
    tenant_id: str = "default",
    priority: str = "normal",
    payload_extra: dict[str, Any] | None = None,
    dedupe_kind: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if scope_type == "cost_statistics":
        for target_scope_key in CostStatisticsRuntimeService.refresh_scope_keys_from_scope_keys([scope_key]):
            _append_single_read_model_refresh(
                refreshes,
                scope_type=scope_type,
                scope_key=target_scope_key,
                reason=reason,
                tenant_id=tenant_id,
                priority=priority,
                payload_extra=payload_extra,
                dedupe_kind=dedupe_kind,
                metadata=metadata,
            )
        return
    _append_single_read_model_refresh(
        refreshes,
        scope_type=scope_type,
        scope_key=scope_key,
        reason=reason,
        tenant_id=tenant_id,
        priority=priority,
        payload_extra=payload_extra,
        dedupe_kind=dedupe_kind,
        metadata=metadata,
    )


def _append_single_read_model_refresh(
    refreshes: list[dict[str, Any]],
    *,
    scope_type: str,
    scope_key: str,
    reason: str,
    tenant_id: str = "default",
    priority: str = "normal",
    payload_extra: dict[str, Any] | None = None,
    dedupe_kind: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    normalized_scope_type = text(scope_type)
    normalized_scope_key = text(scope_key)
    normalized_reason = text(reason) or "workbench_relation_changed"
    normalized_tenant_id = text(tenant_id) or "default"
    normalized_priority = text(priority) or "normal"
    if not normalized_scope_type or not normalized_scope_key:
        return
    event_type = f"{normalized_scope_type}.read_model.refresh"
    normalized_dedupe_kind = text(dedupe_kind)
    dedupe_key = f"{event_type}:{normalized_scope_type}:{normalized_scope_key}"
    if normalized_dedupe_kind:
        dedupe_key = f"{event_type}:{normalized_scope_type}:{normalized_scope_key}:{normalized_dedupe_kind}"
    payload = {
        "scope_type": normalized_scope_type,
        "scope_key": normalized_scope_key,
        "reason": normalized_reason,
        **(payload_extra or {}),
    }
    if metadata:
        payload["metadata"] = dict(metadata)
    refreshes.append(
        {
            "tenant_id": normalized_tenant_id,
            "scope_type": normalized_scope_type,
            "scope_key": normalized_scope_key,
            "reason": normalized_reason,
            "priority": normalized_priority,
            "payload": payload,
            "event_type": event_type,
            "dedupe_key": dedupe_key,
        }
    )


def _enqueue_read_model_refreshes_in_transaction(connection: Any, refreshes: list[dict[str, Any]]) -> None:
    rows = _deduped_read_model_refresh_rows(refreshes)
    if not rows:
        return
    value_sql = ", ".join(
        [
            "(%s::integer, %s::text, %s::text, %s::text, %s::text, %s::text, %s::jsonb, %s::text, %s::text)"
        ]
        * len(rows)
    )
    params = tuple(value for row in rows for value in row)
    connection.fetch_all(
        f"""
        with input(
            ord, tenant_id, scope_type, scope_key, reason, priority,
            payload, event_type, dedupe_key
        ) as (
            values {value_sql}
        ),
        dirty_input as (
            select distinct on (tenant_id, scope_type, scope_key)
                tenant_id,
                scope_type,
                scope_key,
                reason,
                priority,
                payload
            from input
            order by tenant_id, scope_type, scope_key, ord desc
        ),
        dirty as (
            insert into job.read_model_dirty_scopes(
                tenant_id, scope_type, scope_key, reason, payload, raw_payload,
                source_version, status, next_run_at, priority
            )
            select
                dirty_input.tenant_id,
                dirty_input.scope_type,
                dirty_input.scope_key,
                dirty_input.reason,
                dirty_input.payload,
                dirty_input.payload,
                coalesce((
                    select max(existing.source_version) + 1
                    from job.read_model_dirty_scopes existing
                    where existing.tenant_id = dirty_input.tenant_id
                      and existing.scope_type = dirty_input.scope_type
                      and existing.scope_key = dirty_input.scope_key
                ), 0),
                'pending',
                clock_timestamp(),
                dirty_input.priority
            from dirty_input
            on conflict (tenant_id, scope_type, scope_key)
            where status in ('pending', 'processing')
            do update set
                reason = excluded.reason,
                payload = job.read_model_dirty_scopes.payload || excluded.payload,
                raw_payload = excluded.raw_payload,
                source_version = job.read_model_dirty_scopes.source_version + 1,
                status = 'pending',
                next_run_at = clock_timestamp(),
                priority = excluded.priority,
                updated_at = clock_timestamp()
            returning tenant_id, scope_type, scope_key, source_version
        ),
        event_rows as (
            insert into job.outbox_events (
                tenant_id, event_type, aggregate_type, aggregate_id,
                scope_type, scope_key, dedupe_key, schema_version,
                source_version, priority, payload, raw_payload,
                available_at, created_at, updated_at, next_publish_at
            )
            select
                input.tenant_id,
                input.event_type,
                'read_model',
                input.scope_key,
                input.scope_type,
                input.scope_key,
                input.dedupe_key,
                1,
                dirty.source_version,
                input.priority,
                input.payload || jsonb_build_object('source_version', dirty.source_version),
                input.payload || jsonb_build_object('source_version', dirty.source_version),
                clock_timestamp(),
                clock_timestamp(),
                clock_timestamp(),
                clock_timestamp()
            from input
            join dirty
              on dirty.tenant_id = input.tenant_id
             and dirty.scope_type = input.scope_type
             and dirty.scope_key = input.scope_key
            on conflict (tenant_id, dedupe_key)
            where dedupe_key is not null and status = 'pending'
            do update set
                payload = (
                    job.outbox_events.payload
                    || excluded.payload
                    || case
                        when excluded.payload ? 'parent_scope_keys' then jsonb_build_object(
                            'parent_scope_keys',
                            (
                                select coalesce(jsonb_agg(distinct merged.value order by merged.value), '[]'::jsonb)
                                from jsonb_array_elements_text(
                                    coalesce(job.outbox_events.payload->'parent_scope_keys', '[]'::jsonb)
                                    || coalesce(excluded.payload->'parent_scope_keys', '[]'::jsonb)
                                ) as merged(value)
                            )
                        )
                        else '{{}}'::jsonb
                    end
                ),
                raw_payload = (
                    job.outbox_events.raw_payload
                    || excluded.raw_payload
                    || case
                        when excluded.raw_payload ? 'parent_scope_keys' then jsonb_build_object(
                            'parent_scope_keys',
                            (
                                select coalesce(jsonb_agg(distinct merged.value order by merged.value), '[]'::jsonb)
                                from jsonb_array_elements_text(
                                    coalesce(job.outbox_events.raw_payload->'parent_scope_keys', '[]'::jsonb)
                                    || coalesce(excluded.raw_payload->'parent_scope_keys', '[]'::jsonb)
                                ) as merged(value)
                            )
                        )
                        else '{{}}'::jsonb
                    end
                ),
                source_version = greatest(
                    coalesce(job.outbox_events.source_version, 0),
                    coalesce(excluded.source_version, 0)
                ),
                priority = excluded.priority,
                publish_status = 'unpublished',
                published_at = null,
                publish_last_error = null,
                next_publish_at = clock_timestamp(),
                publish_locked_by = null,
                publish_locked_at = null,
                publish_confirmed_at = null,
                updated_at = clock_timestamp()
            returning
                tenant_id,
                dedupe_key
        )
        select event_rows.*
        from event_rows
        join input
          on input.tenant_id = event_rows.tenant_id
         and input.dedupe_key = event_rows.dedupe_key
        order by input.ord
        """,
        params,
    )


def _deduped_read_model_refresh_rows(refreshes: list[dict[str, Any]]) -> list[tuple[object, ...]]:
    deduped: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for refresh in refreshes:
        dedupe_key = text(refresh.get("dedupe_key"))
        if not dedupe_key:
            continue
        payload = dict(refresh.get("payload") if isinstance(refresh.get("payload"), dict) else {})
        existing = deduped.get(dedupe_key)
        if existing is None:
            deduped[dedupe_key] = {**refresh, "payload": payload}
            order.append(dedupe_key)
            continue
        merged_payload = {**dict(existing.get("payload") or {}), **payload}
        parent_scope_keys = _merged_parent_scope_keys(existing.get("payload"), payload)
        if parent_scope_keys:
            merged_payload["parent_scope_keys"] = parent_scope_keys
        existing["payload"] = merged_payload
        existing["reason"] = refresh.get("reason") or existing.get("reason")
        existing["priority"] = refresh.get("priority") or existing.get("priority")

    rows: list[tuple[object, ...]] = []
    for index, dedupe_key in enumerate(order):
        refresh = deduped[dedupe_key]
        rows.append(
            (
                index,
                text(refresh.get("tenant_id")) or "default",
                text(refresh.get("scope_type")) or "",
                text(refresh.get("scope_key")) or "",
                text(refresh.get("reason")) or "workbench_relation_changed",
                text(refresh.get("priority")) or "normal",
                jsonb(refresh.get("payload") if isinstance(refresh.get("payload"), dict) else {}),
                text(refresh.get("event_type")) or "",
                dedupe_key,
            )
        )
    return rows


def _merged_parent_scope_keys(left: Any, right: Any) -> list[str]:
    values: list[str] = []
    for payload in (left, right):
        if not isinstance(payload, dict):
            continue
        for value in list(payload.get("parent_scope_keys") or []):
            normalized = text(value)
            if normalized and normalized not in values:
                values.append(normalized)
    return sorted(values)
