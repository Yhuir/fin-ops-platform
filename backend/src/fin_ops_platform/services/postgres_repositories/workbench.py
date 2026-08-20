from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    event_uuid,
    int_value,
    iter_mapping,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    serialize_value,
    text,
    text_list,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.postgres_snapshot_contracts import (
    normalize_no_oa_bank_batches,
    normalize_turnover_relations,
)
from fin_ops_platform.services.workbench_row_identity import (
    canonical_workbench_row_type,
    parse_workbench_row_identity_key,
    row_type_for_workbench_row_id,
    workbench_row_identity_key,
)

NO_OA_BANK_BATCH_RELATION_MODE = "no_oa_bank_batch"
BANK_FLOW_RULE_BATCH_RELATION_MODE = "bank_flow_rule_batch"
WORKBENCH_ANOMALY_REVIEW_SCENARIO = "workbench_anomaly_review"
LEGACY_OA_INVOICE_AMOUNT_MISMATCH_SCENARIO = "oa_invoice_amount_mismatch"


def _no_oa_batch_relation_mode(payload: Any) -> str:
    if not isinstance(payload, dict):
        return NO_OA_BANK_BATCH_RELATION_MODE
    return text(payload.get("relation_mode")) or NO_OA_BANK_BATCH_RELATION_MODE


def _execute_batch_insert_values(connection: Any, sql: str, params_seq: list[tuple[Any, ...]]) -> int:
    rows = list(params_seq or [])
    if not rows:
        return 0
    execute_many_values = getattr(connection, "execute_many_values", None)
    if callable(execute_many_values):
        return int(execute_many_values(sql, rows) or 0)
    execute_many = getattr(connection, "execute_many", None)
    if callable(execute_many):
        return int(execute_many(sql, rows) or 0)
    affected = 0
    for params in rows:
        affected += int(connection.execute(sql, params) or 0)
    return affected


class PostgresWorkbenchRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._relation_repository = PostgresWorkbenchRelationRepository(connection)

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        return self._relation_repository.load_workbench_pair_relations()

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: set[str] | None = None,
    ) -> None:
        self._relation_repository.save_workbench_pair_relations(snapshot, changed_case_ids=changed_case_ids)

    def load_no_oa_bank_batches(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select batch_id as key, raw_payload from app.no_oa_bank_batches order by batch_id")
        if not rows:
            return {}
        event_rows = self._connection.fetch_all(
            "select raw_payload from app.no_oa_bank_batch_events order by occurred_at, batch_id"
        )
        return normalize_no_oa_bank_batches(
            {str(row.get("key")): row_payload(row, "raw_payload") for row in rows},
            [payload for row in event_rows if isinstance((payload := row_payload(row, "raw_payload")), dict)],
        )

    def load_bank_flow_rule_batches(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            "select batch_id as key, raw_payload from app.bank_flow_rule_batches order by batch_id"
        )
        if not rows:
            return {}
        event_rows = self._connection.fetch_all(
            "select raw_payload from app.bank_flow_rule_batch_events order by occurred_at, batch_id"
        )
        return normalize_no_oa_bank_batches(
            {str(row.get("key")): row_payload(row, "raw_payload") for row in rows},
            [payload for row in event_rows if isinstance((payload := row_payload(row, "raw_payload")), dict)],
        )

    def save_no_oa_bank_batches(
        self,
        snapshot: dict[str, Any],
        *,
        relation_mode: str = NO_OA_BANK_BATCH_RELATION_MODE,
    ) -> None:
        normalized_relation_mode = text(relation_mode) or NO_OA_BANK_BATCH_RELATION_MODE

        def write(connection: Any) -> None:
            batches = snapshot.get("batches") if isinstance(snapshot, dict) else None
            batch_items = [
                (batch_id, payload)
                for batch_id, payload in list(iter_mapping(batches))
                if _no_oa_batch_relation_mode(payload) == normalized_relation_mode
            ]
            batch_ids = [
                str(batch_id).strip()
                for batch_id, _payload in batch_items
                if str(batch_id).strip()
            ]
            if batch_ids:
                connection.execute(
                    """
                    delete from app.no_oa_bank_batch_events
                    where no_oa_bank_batch_id in (
                        select id
                        from app.no_oa_bank_batches
                        where coalesce(nullif(raw_payload->'normalized_payload'->>'relation_mode', ''), 'no_oa_bank_batch') = %s
                          and not (batch_id = any(%s))
                    )
                    """,
                    (normalized_relation_mode, batch_ids),
                )
                connection.execute(
                    """
                    delete from app.no_oa_bank_batches
                    where coalesce(nullif(raw_payload->'normalized_payload'->>'relation_mode', ''), 'no_oa_bank_batch') = %s
                      and not (batch_id = any(%s))
                    """,
                    (normalized_relation_mode, batch_ids),
                )
            else:
                connection.execute(
                    """
                    delete from app.no_oa_bank_batch_events
                    where no_oa_bank_batch_id in (
                        select id
                        from app.no_oa_bank_batches
                        where coalesce(nullif(raw_payload->'normalized_payload'->>'relation_mode', ''), 'no_oa_bank_batch') = %s
                    )
                    """,
                    (normalized_relation_mode,),
                )
                connection.execute(
                    """
                    delete from app.no_oa_bank_batches
                    where coalesce(nullif(raw_payload->'normalized_payload'->>'relation_mode', ''), 'no_oa_bank_batch') = %s
                    """,
                    (normalized_relation_mode,),
                )
            self._upsert_no_oa_bank_batch_items(connection, batch_items)
            self._replace_no_oa_bank_batch_events(
                connection,
                snapshot.get("audit_log") if isinstance(snapshot, dict) else None,
            )

        run_in_transaction(self._connection, write)


    def save_bank_flow_rule_batch_items(
        self,
        snapshot: dict[str, Any],
        *,
        batch_ids: set[str] | list[str] | tuple[str, ...],
    ) -> None:
        normalized_batch_ids = {
            text(batch_id)
            for batch_id in list(batch_ids or [])
            if text(batch_id)
        }
        if not normalized_batch_ids:
            return

        batches = snapshot.get("batches") if isinstance(snapshot, dict) else None
        batch_items = [
            (batch_id, payload)
            for batch_id, payload in list(iter_mapping(batches))
            if _no_oa_batch_relation_mode(payload) == BANK_FLOW_RULE_BATCH_RELATION_MODE
            and (
                text(batch_id) in normalized_batch_ids
                or text(payload.get("batch_id")) in normalized_batch_ids
                or text(payload.get("relation_case_id")) in normalized_batch_ids
            )
        ]
        if not batch_items:
            return
        selected_batch_ids = {
            text(batch_id)
            for batch_id, _payload in batch_items
            if text(batch_id)
        }

        def write(connection: Any) -> None:
            self._upsert_bank_flow_rule_batch_items(connection, batch_items)
            audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else []
            audit_items = audit_log if isinstance(audit_log, list) else []
            scoped_audit_log = [
                item
                for item in audit_items
                if isinstance(item, dict) and text(item.get("batch_id")) in selected_batch_ids
            ]
            self._replace_bank_flow_rule_batch_events(connection, scoped_audit_log)

        run_in_transaction(self._connection, write)

    def _upsert_no_oa_bank_batch_items(
        self,
        connection: Any,
        batch_items: list[tuple[str, dict[str, Any]]],
    ) -> None:
        _execute_batch_insert_values(
            connection,
            """
            insert into app.no_oa_bank_batches(
                batch_id, status, status_bucket, version, scope_month, account_key,
                total_amount, bank_transaction_ids, source_versions, raw_payload
            )
            values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s)
            on conflict (batch_id) do update set
                status = excluded.status,
                status_bucket = excluded.status_bucket,
                version = excluded.version,
                scope_month = excluded.scope_month,
                account_key = excluded.account_key,
                total_amount = excluded.total_amount,
                bank_transaction_ids = excluded.bank_transaction_ids,
                source_versions = excluded.source_versions,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            [self._bank_batch_app_row_params(batch_id, payload) for batch_id, payload in batch_items],
        )

    def _upsert_bank_flow_rule_batch_items(
        self,
        connection: Any,
        batch_items: list[tuple[str, dict[str, Any]]],
    ) -> None:
        normalized_items = [
            (batch_id, {**payload, "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE})
            for batch_id, payload in batch_items
        ]
        _execute_batch_insert_values(
            connection,
            """
            insert into app.bank_flow_rule_batches(
                batch_id, status, status_bucket, version, scope_month, account_key,
                total_amount, bank_transaction_ids, source_versions, raw_payload
            )
            values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s)
            on conflict (batch_id) do update set
                status = excluded.status,
                status_bucket = excluded.status_bucket,
                version = excluded.version,
                scope_month = excluded.scope_month,
                account_key = excluded.account_key,
                total_amount = excluded.total_amount,
                bank_transaction_ids = excluded.bank_transaction_ids,
                source_versions = excluded.source_versions,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            [self._bank_batch_app_row_params(batch_id, payload) for batch_id, payload in normalized_items],
        )

    @staticmethod
    def _bank_batch_app_row_params(batch_id: str, payload: dict[str, Any]) -> tuple[Any, ...]:
        return (
            batch_id,
            text(payload.get("status") or "draft"),
            text(payload.get("status_bucket")),
            int_value(payload.get("version"), 1),
            month_start(payload.get("scope_month") or payload.get("month")),
            text(payload.get("account_key")),
            decimal_text(payload.get("total_amount") or payload.get("amount") or 0),
            text_list(payload.get("bank_transaction_ids") or payload.get("row_ids")),
            jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
            jsonb({"normalized_payload": payload}),
        )

    def load_turnover_relations(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select relation_id as key, raw_payload from app.turnover_relations order by relation_id")
        event_rows = self._connection.fetch_all(
            "select raw_payload from app.turnover_relation_events order by occurred_at, relation_id"
        )
        return normalize_turnover_relations(
            [
                {**payload, "relation_id": payload.get("relation_id") or str(row.get("key"))}
                for row in rows
                if isinstance((payload := row_payload(row, "raw_payload")), dict)
            ],
            [payload for row in event_rows if isinstance((payload := row_payload(row, "raw_payload")), dict)],
        )

    def save_turnover_relations(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            relations = snapshot.get("relations") if isinstance(snapshot, dict) else None
            for relation_id, payload in self._iter_relation_items(relations):
                self._upsert_turnover_relation(
                    connection,
                    relation_id=relation_id,
                    payload=payload,
                    audit_payload=snapshot.get("audit_log") if isinstance(snapshot.get("audit_log"), list) else [],
                )
            self._replace_turnover_relation_events(
                connection,
                snapshot.get("audit_log") if isinstance(snapshot, dict) else None,
            )

        run_in_transaction(self._connection, write)

    def save_turnover_relation_change(
        self,
        *,
        relation: dict[str, Any],
        audit_event: dict[str, Any],
    ) -> None:
        """Persist one command result without rewriting unrelated relations."""
        relation_id = text(relation.get("relation_id"))
        if not relation_id:
            raise ValueError("turnover relation change requires relation_id.")
        if text(audit_event.get("relation_id")) != relation_id:
            raise ValueError("turnover relation audit event must match relation_id.")

        def write(connection: Any) -> None:
            self._upsert_turnover_relation(
                connection,
                relation_id=relation_id,
                payload=relation,
                audit_payload=[audit_event],
            )
            self._insert_turnover_relation_event(connection, audit_event)

        run_in_transaction(self._connection, write)

    @staticmethod
    def _upsert_turnover_relation(
        connection: Any,
        *,
        relation_id: str,
        payload: dict[str, Any],
        audit_payload: Any,
    ) -> None:
        bank_transaction_ids = text_list(payload.get("bank_transaction_ids") or payload.get("bank_row_ids"))
        connection.execute(
            """
            insert into app.turnover_relations(
                relation_id, bank_transaction_id, status, relation_type, scope_month,
                counterparty_name, amount, version, audit_payload, source_versions, raw_payload
            )
            values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s)
            on conflict (relation_id) do update set
                bank_transaction_id = excluded.bank_transaction_id,
                status = excluded.status,
                relation_type = excluded.relation_type,
                scope_month = excluded.scope_month,
                counterparty_name = excluded.counterparty_name,
                amount = excluded.amount,
                version = excluded.version,
                audit_payload = excluded.audit_payload,
                source_versions = excluded.source_versions,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                relation_id,
                bank_transaction_ids[0] if bank_transaction_ids else text(payload.get("bank_transaction_id")),
                text(payload.get("status") or "active"),
                text(payload.get("relation_type") or payload.get("type")),
                month_start(payload.get("scope_month") or payload.get("month")),
                text(payload.get("counterparty_name")),
                decimal_text(payload.get("amount")),
                int_value(payload.get("version"), 1),
                jsonb(audit_payload if isinstance(audit_payload, list) else []),
                jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                jsonb({"normalized_payload": payload}),
            ),
        )

    @staticmethod
    def _insert_turnover_relation_event(connection: Any, item: dict[str, Any]) -> None:
        relation_id = text(item.get("relation_id"))
        if not relation_id:
            raise ValueError("turnover relation event requires relation_id.")
        connection.execute(
            """
            insert into app.turnover_relation_events(
                id, turnover_relation_id, relation_id, event_type, actor_id, occurred_at, payload, raw_payload
            )
            values (
                %s::uuid,
                (select id from app.turnover_relations where relation_id = %s limit 1),
                %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s
            )
            on conflict (id) do update set payload = excluded.payload, raw_payload = excluded.raw_payload
            """,
            (
                event_uuid("turnover_relation_events", relation_id, item),
                relation_id,
                relation_id,
                text(item.get("action") or item.get("event_type") or item.get("operation") or "updated"),
                text(item.get("actor") or item.get("actor_id") or item.get("updated_by")),
                text(item.get("created_at") or item.get("occurred_at") or item.get("updated_at")),
                jsonb(item),
                jsonb({"normalized_payload": item}),
            ),
        )

    def load_turnover_relation_audit_log(self) -> list[Any]:
        snapshot = self.load_turnover_relations()
        audit_log = snapshot.get("audit_log") if isinstance(snapshot, dict) else None
        return list(audit_log) if isinstance(audit_log, list) else []

    def save_turnover_relation_audit_log(
        self,
        snapshot: list[Any],
        *,
        load_snapshot: Callable[[], dict[str, Any]],
        save_snapshot: Callable[[dict[str, Any]], None],
    ) -> None:
        payload = load_snapshot()
        payload["audit_log"] = list(snapshot)
        save_snapshot(payload)

    def load_turnover_ledger_extras(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            "select ledger_key as key, extra_payload, raw_payload from app.turnover_ledger_extras order by ledger_key"
        )
        if not rows:
            return {}
        return {"extras": {str(row.get("key")): row_payload(row, "extra_payload", "raw_payload") for row in rows}}

    def load_turnover_ledger_extra_for_update(self, ledger_key: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            select ledger_key as key, extra_payload, raw_payload
            from app.turnover_ledger_extras
            where ledger_key = %s
            for update
            """,
            (str(ledger_key or "").strip(),),
        )
        if not row:
            return None
        payload = row_payload(row, "extra_payload", "raw_payload")
        return dict(payload) if isinstance(payload, dict) else None

    def save_turnover_ledger_extras(self, snapshot: dict[str, Any]) -> None:
        extras = snapshot.get("extras") if isinstance(snapshot, dict) else None
        for ledger_key, payload in iter_mapping(extras):
            self._connection.execute(
                """
                insert into app.turnover_ledger_extras(ledger_key, scope_month, extra_payload, raw_payload, updated_by)
                values (%s, %s::date, %s, %s, %s)
                on conflict (ledger_key) do update set
                    scope_month = excluded.scope_month,
                    extra_payload = excluded.extra_payload,
                    raw_payload = excluded.raw_payload,
                    updated_by = excluded.updated_by,
                    updated_at = now()
                """,
                (
                    ledger_key,
                    month_start(payload.get("scope_month") or payload.get("month")),
                    jsonb(payload),
                    jsonb({"normalized_payload": payload}),
                    text(payload.get("updated_by") or payload.get("actor_id")),
                ),
            )

    def save_workbench_overrides(self, workbench_overrides_snapshot: dict[str, Any], *, changed_row_ids: set[str] | None = None) -> None:
        overrides = workbench_overrides_snapshot.get("overrides") if isinstance(workbench_overrides_snapshot, dict) else None
        row_overrides = workbench_overrides_snapshot.get("row_overrides") if isinstance(workbench_overrides_snapshot, dict) else None
        payload_map = overrides if isinstance(overrides, dict) else row_overrides if isinstance(row_overrides, dict) else {}
        changed_ids = {str(item) for item in changed_row_ids} if changed_row_ids is not None else None
        for identity_key, payload in iter_mapping(payload_map):
            parsed_identity = parse_workbench_row_identity_key(identity_key)
            payload_row_id = text(payload.get("row_id"))
            payload_row_type = canonical_workbench_row_type(
                payload.get("row_type") or payload.get("type"),
                unknown="",
            )
            if parsed_identity is not None:
                parsed_row_type, parsed_row_id = parsed_identity
                if payload_row_id and payload_row_id != parsed_row_id:
                    raise ValueError("Workbench override key and payload row ids do not match.")
                if payload_row_type and payload_row_type != parsed_row_type:
                    raise ValueError("Workbench override key and payload row types do not match.")
                row_id = parsed_row_id
                row_type = parsed_row_type
            else:
                row_id = payload_row_id or identity_key
                row_type = payload_row_type or row_type_for_workbench_row_id(
                    row_id,
                    unknown="unknown",
                )
            if changed_ids is not None and row_id not in changed_ids:
                continue
            legacy_identity = (
                workbench_row_identity_key(row_type, row_id)
                if row_type != "unknown"
                else row_id
            )
            self._connection.execute(
                """
                insert into app.workbench_row_overrides(
                    legacy_mongo_id, row_id, row_type, scope_month, status, projection_version,
                    override_payload, source_versions, changed_row_ids, updated_by, raw_payload
                )
                values (%s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s)
                on conflict (row_id, row_type) do update set
                    scope_month = excluded.scope_month,
                    status = excluded.status,
                    projection_version = excluded.projection_version,
                    override_payload = excluded.override_payload,
                    source_versions = excluded.source_versions,
                    changed_row_ids = excluded.changed_row_ids,
                    updated_by = excluded.updated_by,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                """,
                (
                    legacy_identity,
                    row_id,
                    row_type,
                    month_start(payload.get("scope_month") or payload.get("month")),
                    text(payload.get("status") or "active"),
                    int_value(payload.get("projection_version"), 1),
                    jsonb(payload),
                    jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                    text_list(changed_row_ids or [row_id]),
                    text(payload.get("updated_by") or payload.get("actor_id")),
                    jsonb({"normalized_payload": payload}),
                ),
            )

    def load_workbench_overrides(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            """
            select row_id, row_type, override_payload, raw_payload
            from app.workbench_row_overrides
            where status = 'active'
              and row_type in ('oa', 'bank', 'invoice')
            order by row_type, row_id
            """
        )
        if not rows:
            return {}
        row_overrides: dict[str, dict[str, Any]] = {}
        for row in rows:
            row_id = str(row.get("row_id") or "").strip()
            row_type = canonical_workbench_row_type(row.get("row_type"), unknown="")
            payload = row_payload(row, "override_payload", "raw_payload")
            if not row_id or not isinstance(payload, dict):
                continue
            normalized_payload = dict(payload)
            if row_type:
                normalized_payload["row_id"] = row_id
                normalized_payload["row_type"] = row_type
                key = workbench_row_identity_key(row_type, row_id)
            else:
                key = row_id
            row_overrides[key] = normalized_payload
        case_counter = 0
        for payload in row_overrides.values():
            if not isinstance(payload, dict):
                continue
            for field_name in ("case_id", "exception_case_id"):
                raw_case_id = str(payload.get(field_name) or "")
                if not raw_case_id.startswith("CASE-AUTO-"):
                    continue
                try:
                    case_counter = max(case_counter, int(raw_case_id.removeprefix("CASE-AUTO-")))
                except ValueError:
                    continue
        return {"case_counter": case_counter, "row_overrides": row_overrides}

    def load_workbench_exception_cases(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            """
            select case_id as key, raw_payload
            from app.workbench_exception_cases
            where scenario is null or scenario not in (%s, %s)
            order by case_id
            """,
            (
                LEGACY_OA_INVOICE_AMOUNT_MISMATCH_SCENARIO,
                WORKBENCH_ANOMALY_REVIEW_SCENARIO,
            ),
        )
        if not rows:
            return {}
        return {
            "cases": {
                str(row.get("key")): row_payload(row, "raw_payload")
                for row in rows
            }
        }

    def repair_legacy_workbench_typed_identities(
        self,
        *,
        tenant_id: str,
    ) -> dict[str, int]:
        normalized_tenant_id = text(tenant_id)
        if not normalized_tenant_id:
            raise ValueError("tenant_id is required for legacy workbench identity repair.")

        def repair(connection: Any) -> dict[str, int]:
            from fin_ops_platform.services.postgres_repositories.workbench_page_selection import (
                PostgresWorkbenchPageSelectionRepository,
            )

            identity_resolver = PostgresWorkbenchPageSelectionRepository(
                connection,
                tenant_id=normalized_tenant_id,
            ).resolve_canonical_identity_type_candidates_in_current_transaction
            override_counts = self._repair_locked_legacy_workbench_override_identities(
                connection,
                identity_resolver=identity_resolver,
            )
            locked_rows = connection.fetch_all(
                """
                select case_id as key, raw_payload
                from app.workbench_exception_cases
                where (scenario is null or scenario not in (%s, %s))
                  and jsonb_typeof(raw_payload#>'{normalized_payload,row_ids}') = 'array'
                  and jsonb_typeof(raw_payload#>'{normalized_payload,row_types}') = 'array'
                  and jsonb_array_length(raw_payload#>'{normalized_payload,row_ids}')
                      <> jsonb_array_length(raw_payload#>'{normalized_payload,row_types}')
                order by case_id
                for update
                """,
                (
                    LEGACY_OA_INVOICE_AMOUNT_MISMATCH_SCENARIO,
                    WORKBENCH_ANOMALY_REVIEW_SCENARIO,
                ),
            )
            exception_repaired = self._repair_locked_legacy_workbench_exception_case_identities(
                connection,
                locked_rows,
                identity_resolver=identity_resolver,
            )
            counts = {
                **override_counts,
                "exception_repaired": exception_repaired,
            }
            if counts["override_repaired"] + counts["exception_repaired"] > 0:
                audit_payload = {
                    **counts,
                    "contract_schema": "workbench_typed_identity",
                    "contract_version": 1,
                }
                connection.execute(
                    """
                    insert into audit.events(
                        event_type, object_type, object_id, actor_id, scope,
                        payload, raw_payload
                    ) values (
                        'workbench.legacy_typed_identity.repaired',
                        'workbench_typed_identity_contract',
                        'workbench_typed_identity:v1',
                        'system:direct-api-bootstrap',
                        %s,
                        %s,
                        %s
                    )
                    """,
                    (
                        normalized_tenant_id,
                        jsonb(audit_payload),
                        jsonb({"normalized_payload": audit_payload}),
                    ),
                )
            return counts

        return run_in_transaction(self._connection, repair)

    @classmethod
    def _repair_locked_legacy_workbench_override_identities(
        cls,
        connection: Any,
        *,
        identity_resolver: Callable[[list[str]], dict[str, list[str]]],
    ) -> dict[str, int]:
        locked_rows = connection.fetch_all(
            """
            select id::text as override_id, row_id, override_payload, raw_payload
            from app.workbench_row_overrides
            where status = 'active'
              and lower(btrim(row_type)) = 'unknown'
            order by id
            for update
            """
        )
        if not locked_rows:
            return {
                "override_repaired": 0,
                "override_unresolved_missing_source": 0,
            }

        requested_row_ids = sorted(
            {
                row_id
                for row in locked_rows
                if (row_id := text(row.get("row_id")))
            }
        )
        source_hits_by_row_id = identity_resolver(requested_row_ids)
        repaired_count = 0
        unresolved_count = 0
        for row in locked_rows:
            override_id = text(row.get("override_id"))
            row_id = text(row.get("row_id"))
            payload = row_payload(row, "override_payload", "raw_payload")
            if not override_id or not row_id or not isinstance(payload, dict):
                raise ValueError("Legacy workbench override has invalid persisted identity or payload.")
            source_hits = sorted(source_hits_by_row_id.get(row_id, []))
            if len(source_hits) > 1:
                raise ValueError(
                    f"Legacy workbench override row {row_id} resolves to multiple canonical source rows: "
                    + ", ".join(source_hits)
                )
            if not source_hits:
                unresolved_count += 1
                continue

            row_type = source_hits[0]
            composite_identity = workbench_row_identity_key(row_type, row_id)
            collision = connection.fetch_one(
                """
                select id::text as override_id
                from app.workbench_row_overrides
                where id <> %s::uuid
                  and (
                        (row_id = %s and row_type = %s)
                        or legacy_mongo_id = %s
                  )
                for update
                """,
                (override_id, row_id, row_type, composite_identity),
            )
            if collision:
                raise ValueError(
                    f"Legacy workbench override row {row_id} collides with typed identity "
                    f"{row_type}:{row_id}."
                )
            normalized_payload = dict(payload)
            normalized_payload["row_id"] = row_id
            normalized_payload["row_type"] = row_type
            normalized_payload["legacy_identity_repair"] = {
                "status": "typed",
            }
            affected = connection.execute(
                """
                update app.workbench_row_overrides
                set legacy_mongo_id = %s,
                    row_type = %s,
                    override_payload = %s,
                    raw_payload = %s,
                    updated_at = now()
                where id = %s::uuid
                  and status = 'active'
                  and lower(btrim(row_type)) = 'unknown'
                """,
                (
                    composite_identity,
                    row_type,
                    jsonb(normalized_payload),
                    jsonb({"normalized_payload": normalized_payload}),
                    override_id,
                ),
            )
            if affected != 1:
                raise RuntimeError(
                    f"Legacy workbench override repair lost its locked row: {override_id}"
                )
            repaired_count += 1
        return {
            "override_repaired": repaired_count,
            "override_unresolved_missing_source": unresolved_count,
        }

    @staticmethod
    def _workbench_exception_case_needs_typed_identity_repair(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        row_ids = payload.get("row_ids")
        row_types = payload.get("row_types")
        return (
            isinstance(row_ids, list)
            and isinstance(row_types, list)
            and len(row_ids) != len(row_types)
        )

    @classmethod
    def _repair_locked_legacy_workbench_exception_case_identities(
        cls,
        connection: Any,
        locked_rows: list[dict[str, Any]],
        *,
        identity_resolver: Callable[[list[str]], dict[str, list[str]]],
    ) -> int:
        malformed_cases: dict[str, tuple[dict[str, Any], list[str]]] = {}
        for row in locked_rows:
            case_id = str(row.get("key") or "").strip()
            payload = row_payload(row, "raw_payload")
            if not cls._workbench_exception_case_needs_typed_identity_repair(payload):
                continue
            raw_row_ids = payload.get("row_ids")
            if not isinstance(raw_row_ids, list):
                raise ValueError(f"Legacy workbench exception case {case_id} has invalid row_ids.")
            row_ids = [str(value or "").strip() for value in raw_row_ids]
            if not row_ids or any(not row_id for row_id in row_ids):
                raise ValueError(f"Legacy workbench exception case {case_id} has invalid row_ids.")
            malformed_cases[case_id] = (payload, row_ids)

        if not malformed_cases:
            return 0

        requested_row_ids = sorted(
            {
                row_id
                for _payload, row_ids in malformed_cases.values()
                for row_id in row_ids
            }
        )
        source_hits_by_row_id = identity_resolver(requested_row_ids)

        repaired: dict[str, dict[str, Any]] = {}
        for case_id, (payload, row_ids) in malformed_cases.items():
            row_types: list[str] = []
            for row_id in row_ids:
                source_hits = sorted(source_hits_by_row_id.get(row_id, []))
                if not source_hits:
                    raise ValueError(
                        f"Legacy workbench exception case {case_id} row {row_id} "
                        "has no canonical source row."
                    )
                if len(source_hits) != 1:
                    raise ValueError(
                        f"Legacy workbench exception case {case_id} row {row_id} "
                        "resolves to multiple canonical source rows: "
                        + ", ".join(source_hits)
                    )
                row_types.append(source_hits[0])
            normalized_payload = dict(payload)
            normalized_payload["row_ids"] = row_ids
            normalized_payload["row_types"] = row_types
            repaired[case_id] = normalized_payload

        for case_id, normalized_payload in repaired.items():
            affected = connection.execute(
                """
                update app.workbench_exception_cases
                set row_ids = %s,
                    raw_payload = %s
                where case_id = %s
                """,
                (
                    normalized_payload["row_ids"],
                    jsonb({"normalized_payload": normalized_payload}),
                    case_id,
                ),
            )
            if affected != 1:
                raise RuntimeError(
                    f"Legacy workbench exception case repair lost its locked row: {case_id}"
                )
        return len(repaired)

    def load_workbench_anomaly_review_decisions(
        self,
        *,
        scope_key: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        normalized_scope_key = str(scope_key or "").strip()
        scope_clause = (
            "and (scope_month = %s::date or scope_month is null)"
            if normalized_scope_key and normalized_scope_key != "all"
            else ""
        )
        params: tuple[Any, ...] = (WORKBENCH_ANOMALY_REVIEW_SCENARIO,)
        if scope_clause:
            params = (*params, month_start(normalized_scope_key))
        rows = self._connection.fetch_all(
            f"""
            select fingerprint, resolution, updated_by, updated_at,
                   raw_payload#>>'{{normalized_payload,note}}' as note
            from (
                select
                    raw_payload#>>'{{normalized_payload,fingerprint}}' as fingerprint,
                    resolution,
                    updated_by,
                    updated_at,
                    raw_payload,
                    row_number() over (
                        partition by raw_payload#>>'{{normalized_payload,fingerprint}}'
                        order by updated_at desc, version desc, case_id desc
                    ) as decision_rank
                from app.workbench_exception_cases
                where scenario = %s
                  {scope_clause}
            ) latest_decisions
            where decision_rank = 1
            """,
            params,
        )
        return {
            fingerprint: {
                "decision": text(row.get("resolution")),
                "note": text(row.get("note")),
                "reviewed_by": text(row.get("updated_by")),
                "reviewed_at": serialize_value(row.get("updated_at")),
            }
            for row in rows
            if (fingerprint := text(row.get("fingerprint")))
            and text(row.get("resolution")) in {"accept_paired", "keep_unpaired"}
        }

    def set_workbench_anomaly_review_decision(
        self,
        *,
        fingerprint: str,
        group_id: str,
        scope_key: str,
        actor_id: str,
        decision: str,
        note: str,
        detected_classification_codes: list[str],
        evidence_item_fingerprints: list[str],
    ) -> dict[str, Any]:
        normalized_fingerprint = str(fingerprint or "").strip().lower()
        normalized_group_id = str(group_id or "").strip()
        normalized_scope_key = str(scope_key or "").strip()
        normalized_actor_id = str(actor_id or "").strip()
        normalized_decision = str(decision or "").strip()
        normalized_note = str(note or "").strip()
        normalized_detected_codes = sorted(
            dict.fromkeys(
                str(value or "").strip()
                for value in detected_classification_codes
                if str(value or "").strip()
            )
        )
        normalized_evidence_fingerprints = sorted(
            dict.fromkeys(
                str(value or "").strip().lower()
                for value in evidence_item_fingerprints
                if str(value or "").strip()
            )
        )
        if len(normalized_fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in normalized_fingerprint
        ):
            raise ValueError("fingerprint must be a SHA-256 hex digest.")
        if not normalized_group_id or not normalized_scope_key or not normalized_actor_id:
            raise ValueError("group_id, scope_key and actor_id are required.")
        if normalized_decision not in {"accept_paired", "keep_unpaired"}:
            raise ValueError("decision must be accept_paired or keep_unpaired.")
        case_id = f"ANOMALY-REVIEW-{normalized_fingerprint[:32]}"

        def write(connection: Any) -> dict[str, Any]:
            current = connection.fetch_one(
                """
                select id::text as id, status, resolution, version, created_by, created_at,
                       scope_month::text as scope_month,
                       raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
                           as evidence_item_fingerprints,
                       raw_payload#>'{normalized_payload,detected_classification_codes}'
                           as detected_classification_codes,
                       raw_payload#>>'{normalized_payload,note}' as note
                from app.workbench_exception_cases
                where case_id = %s
                for update
                """,
                (case_id,),
            )
            current_resolution = text((current or {}).get("resolution"))
            current_version = int_value((current or {}).get("version"), 0)
            normalized_scope_month = month_start(normalized_scope_key)
            current_scope_month = (
                (current or {}).get("scope_month") if current else None
            )
            changed = (
                current_resolution != normalized_decision
                or current_scope_month != normalized_scope_month
                or text((current or {}).get("note")) != normalized_note
                or sorted(text_list((current or {}).get("evidence_item_fingerprints")))
                != normalized_evidence_fingerprints
                or sorted(text_list((current or {}).get("detected_classification_codes")))
                != normalized_detected_codes
            )
            next_version = max(1, current_version + (1 if changed else 0))
            normalized_payload = {
                "case_id": case_id,
                "status": "resolved",
                "version": next_version,
                "business_line": "reconciliation_workbench",
                "scenario_code": WORKBENCH_ANOMALY_REVIEW_SCENARIO,
                "fingerprint": normalized_fingerprint,
                "group_id": normalized_group_id,
                "scope_month": normalized_scope_key,
                "decision": normalized_decision,
                "note": normalized_note,
                "detected_classification_codes": normalized_detected_codes,
                "evidence_item_fingerprints": normalized_evidence_fingerprints,
                "row_ids": [],
                "candidate_ids": [],
                "updated_by": normalized_actor_id,
            }
            if not changed:
                return {
                    **normalized_payload,
                    "changed": False,
                }
            connection.execute(
                """
                insert into app.workbench_exception_cases(
                    case_id, status, resolution, version, business_line, scenario, scope_month,
                    row_ids, candidate_ids, created_by, updated_by, raw_payload
                )
                values (%s, 'resolved', %s, %s, 'reconciliation_workbench', %s, %s::date,
                        array[]::text[], array[]::text[], %s, %s, %s)
                on conflict (case_id) do update set
                    status = excluded.status,
                    resolution = excluded.resolution,
                    version = excluded.version,
                    scope_month = excluded.scope_month,
                    updated_by = excluded.updated_by,
                    updated_at = now(),
                    raw_payload = excluded.raw_payload
                """,
                (
                    case_id,
                    normalized_decision,
                    next_version,
                    WORKBENCH_ANOMALY_REVIEW_SCENARIO,
                    normalized_scope_month,
                    normalized_actor_id,
                    normalized_actor_id,
                    jsonb({"normalized_payload": normalized_payload}),
                ),
            )
            connection.execute(
                """
                insert into app.workbench_exception_case_events(
                    exception_case_id, case_id, event_type, actor_id, payload, raw_payload
                )
                values (
                    (select id from app.workbench_exception_cases where case_id = %s),
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    case_id,
                    case_id,
                    "workbench_anomaly_acceptance_withdrawn"
                    if current_resolution == "accept_paired"
                    and normalized_decision == "keep_unpaired"
                    else "workbench_anomaly_reviewed",
                    normalized_actor_id,
                    jsonb(normalized_payload),
                    jsonb({"normalized_payload": normalized_payload}),
                ),
            )
            return {
                **normalized_payload,
                "changed": changed,
            }

        return run_in_transaction(self._connection, write)

    def save_workbench_exception_cases(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            cases = snapshot.get("cases") if isinstance(snapshot, dict) else None
            for case_id, payload in iter_mapping(cases):
                audit = payload.get("audit") if isinstance(payload.get("audit"), list) else []
                connection.execute(
                    """
                    insert into app.workbench_exception_cases(
                        legacy_mongo_id, case_id, status, version, business_line, scenario, resolution,
                        scope_month, row_ids, candidate_ids, source_versions, history_payload,
                        created_by, created_at, updated_by, updated_at, raw_payload
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, coalesce(%s::timestamptz, now()), %s)
                    on conflict (case_id) do update set
                        status = excluded.status,
                        version = excluded.version,
                        business_line = excluded.business_line,
                        scenario = excluded.scenario,
                        resolution = excluded.resolution,
                        scope_month = excluded.scope_month,
                        row_ids = excluded.row_ids,
                        candidate_ids = excluded.candidate_ids,
                        source_versions = excluded.source_versions,
                        history_payload = excluded.history_payload,
                        updated_by = excluded.updated_by,
                        updated_at = excluded.updated_at,
                        raw_payload = excluded.raw_payload
                    """,
                    (
                        case_id,
                        case_id,
                        text(payload.get("status") or "active"),
                        int_value(payload.get("version"), 1),
                        text(payload.get("business_line")),
                        text(payload.get("scenario_code") or payload.get("scenario")),
                        text(payload.get("resolution")),
                        month_start((payload.get("scope_months") or [None])[0] if isinstance(payload.get("scope_months"), list) else payload.get("scope_month")),
                        text_list(payload.get("row_ids")),
                        text_list(payload.get("candidate_ids")),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        jsonb(audit),
                        text(payload.get("created_by")),
                        text(payload.get("created_at")),
                        text(payload.get("updated_by")),
                        text(payload.get("updated_at")),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            self._replace_workbench_exception_case_events(connection, cases)

        run_in_transaction(self._connection, write)

    def _replace_no_oa_bank_batch_events(self, connection: Any, audit_log: Any) -> None:
        if not isinstance(audit_log, list):
            return
        batch_ids = {text(item.get("batch_id")) for item in audit_log if isinstance(item, dict)}
        for batch_id in sorted(item for item in batch_ids if item):
            connection.execute("delete from app.no_oa_bank_batch_events where batch_id = %s", (batch_id,))
        for item in audit_log:
            if not isinstance(item, dict):
                continue
            batch_id = text(item.get("batch_id"))
            if not batch_id:
                continue
            connection.execute(
                """
                insert into app.no_oa_bank_batch_events(
                    id, no_oa_bank_batch_id, batch_id, event_type, actor_id, occurred_at, payload, raw_payload
                )
                values (
                    %s::uuid,
                    (select id from app.no_oa_bank_batches where batch_id = %s limit 1),
                    %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s
                )
                on conflict (id) do update set payload = excluded.payload, raw_payload = excluded.raw_payload
                """,
                (
                    event_uuid("no_oa_bank_batch_events", batch_id, item),
                    batch_id,
                    batch_id,
                    text(item.get("operation") or item.get("event_type") or "unknown"),
                    text(item.get("actor") or item.get("actor_id")),
                    text(item.get("created_at") or item.get("occurred_at")),
                    jsonb(item),
                    jsonb({"normalized_payload": item}),
                ),
            )

    def _replace_bank_flow_rule_batch_events(self, connection: Any, audit_log: Any) -> None:
        if not isinstance(audit_log, list):
            return
        batch_ids = {text(item.get("batch_id")) for item in audit_log if isinstance(item, dict)}
        for batch_id in sorted(item for item in batch_ids if item):
            connection.execute("delete from app.bank_flow_rule_batch_events where batch_id = %s", (batch_id,))
        for item in audit_log:
            if not isinstance(item, dict):
                continue
            batch_id = text(item.get("batch_id"))
            if not batch_id:
                continue
            normalized_item = {**item, "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE}
            connection.execute(
                """
                insert into app.bank_flow_rule_batch_events(
                    id, bank_flow_rule_batch_id, batch_id, event_type, actor_id, occurred_at, payload, raw_payload
                )
                values (
                    %s::uuid,
                    (select id from app.bank_flow_rule_batches where batch_id = %s limit 1),
                    %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s
                )
                on conflict (id) do update set payload = excluded.payload, raw_payload = excluded.raw_payload
                """,
                (
                    event_uuid("bank_flow_rule_batch_events", batch_id, normalized_item),
                    batch_id,
                    batch_id,
                    text(normalized_item.get("operation") or normalized_item.get("event_type") or "unknown"),
                    text(normalized_item.get("actor") or normalized_item.get("actor_id")),
                    text(normalized_item.get("created_at") or normalized_item.get("occurred_at")),
                    jsonb(normalized_item),
                    jsonb({"normalized_payload": normalized_item}),
                ),
            )

    def _replace_turnover_relation_events(self, connection: Any, audit_log: Any) -> None:
        if not isinstance(audit_log, list):
            return
        relation_ids = {text(item.get("relation_id")) for item in audit_log if isinstance(item, dict)}
        for relation_id in sorted(item for item in relation_ids if item):
            connection.execute("delete from app.turnover_relation_events where relation_id = %s", (relation_id,))
        for item in audit_log:
            if not isinstance(item, dict):
                continue
            relation_id = text(item.get("relation_id"))
            if not relation_id:
                continue
            self._insert_turnover_relation_event(connection, item)

    def _replace_workbench_exception_case_events(self, connection: Any, cases: Any) -> None:
        if not isinstance(cases, dict):
            return
        for case_id, payload in iter_mapping(cases):
            audit = payload.get("audit") if isinstance(payload.get("audit"), list) else []
            connection.execute("delete from app.workbench_exception_case_events where case_id = %s", (case_id,))
            for item in audit:
                if not isinstance(item, dict):
                    continue
                connection.execute(
                    """
                    insert into app.workbench_exception_case_events(
                        id, exception_case_id, case_id, event_type, actor_id, occurred_at, payload, raw_payload
                    )
                    values (
                        %s::uuid,
                        (select id from app.workbench_exception_cases where case_id = %s limit 1),
                        %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s
                    )
                    on conflict (id) do update set payload = excluded.payload, raw_payload = excluded.raw_payload
                    """,
                    (
                        event_uuid("workbench_exception_case_events", case_id, item),
                        case_id,
                        case_id,
                        text(item.get("event") or item.get("event_type") or "updated"),
                        text(item.get("actor") or item.get("actor_id")),
                        text(item.get("at") or item.get("created_at") or item.get("occurred_at")),
                        jsonb(item.get("payload") if isinstance(item.get("payload"), dict) else item),
                        jsonb({"normalized_payload": item}),
                    ),
                )

    @staticmethod
    def _iter_relation_items(value: Any) -> list[tuple[str, dict[str, Any]]]:
        if isinstance(value, list):
            pairs: list[tuple[str, dict[str, Any]]] = []
            for raw_payload in value:
                payload = serialize_value(raw_payload)
                if not isinstance(payload, dict):
                    continue
                relation_id = text(payload.get("relation_id") or payload.get("id"))
                if relation_id:
                    pairs.append((relation_id, payload))
            return pairs
        return iter_mapping(value)
