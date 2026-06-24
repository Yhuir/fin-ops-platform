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
    normalize_bank_transaction_categories,
    normalize_no_oa_bank_batches,
    normalize_turnover_relations,
)


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

    def save_no_oa_bank_batches(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            batches = snapshot.get("batches") if isinstance(snapshot, dict) else None
            batch_items = list(iter_mapping(batches))
            batch_ids = [
                str(batch_id).strip()
                for batch_id, _payload in batch_items
                if str(batch_id).strip()
            ]
            if batch_ids:
                connection.execute(
                    "delete from read_model.no_oa_bank_batch_rows where not (batch_id = any(%s))",
                    (batch_ids,),
                )
                connection.execute(
                    """
                    delete from app.no_oa_bank_batch_events
                    where no_oa_bank_batch_id in (
                        select id from app.no_oa_bank_batches where not (batch_id = any(%s))
                    )
                    """,
                    (batch_ids,),
                )
                connection.execute(
                    "delete from app.no_oa_bank_batches where not (batch_id = any(%s))",
                    (batch_ids,),
                )
            else:
                connection.execute("delete from read_model.no_oa_bank_batch_rows")
                connection.execute("delete from app.no_oa_bank_batch_events")
                connection.execute("delete from app.no_oa_bank_batches")
            for batch_id, payload in batch_items:
                connection.execute(
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
                    (
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
                    ),
                )
                row_ids = text_list(payload.get("bank_transaction_ids") or payload.get("row_ids"))
                connection.execute(
                    """
                    insert into read_model.no_oa_bank_batch_rows(
                        batch_id, scope_month, batch_type, status, status_bucket, account_key,
                        total_amount, row_count, submitted_at, withdrawn_at, source_versions,
                        generated_at, cache_status, payload, raw_payload
                    )
                    values (
                        %s, %s::date, %s, %s, %s, %s, %s, %s, %s::timestamptz, %s::timestamptz,
                        %s, coalesce(%s::timestamptz, now()), %s, %s, %s
                    )
                    on conflict (batch_id) do update set
                        scope_month = excluded.scope_month,
                        batch_type = excluded.batch_type,
                        status = excluded.status,
                        status_bucket = excluded.status_bucket,
                        account_key = excluded.account_key,
                        total_amount = excluded.total_amount,
                        row_count = excluded.row_count,
                        submitted_at = excluded.submitted_at,
                        withdrawn_at = excluded.withdrawn_at,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        batch_id,
                        month_start(payload.get("scope_month") or payload.get("month")),
                        text(payload.get("batch_type") or payload.get("type")),
                        text(payload.get("status") or "draft") or "draft",
                        text(payload.get("status_bucket")),
                        text(payload.get("account_key")),
                        decimal_text(payload.get("total_amount") or payload.get("amount") or 0) or "0",
                        int_value(payload.get("row_count"), len(row_ids)),
                        text(payload.get("submitted_at")),
                        text(payload.get("withdrawn_at")),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        text(payload.get("updated_at") or payload.get("generated_at")),
                        text(payload.get("cache_status") or "fresh") or "fresh",
                        jsonb(serialize_value(payload)),
                        jsonb({"normalized_payload": serialize_value(payload)}),
                    ),
                )
            self._replace_no_oa_bank_batch_events(
                connection,
                snapshot.get("audit_log") if isinstance(snapshot, dict) else None,
            )

        run_in_transaction(self._connection, write)

    def load_bank_transaction_categories(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            "select coalesce(legacy_transaction_id, id::text) as key, raw_payload from app.bank_transaction_categories order by key"
        )
        event_rows = self._connection.fetch_all(
            "select raw_payload from app.bank_transaction_category_events order by occurred_at"
        )
        confirmation_rows = self._connection.fetch_all(
            """
            select coalesce(legacy_transaction_id, bank_transaction_id::text) as key,
                   category_code, candidate_category_codes, rule_version, version,
                   confirmed_by, confirmed_at, raw_payload
            from app.bank_transaction_category_confirmations
            where status = 'active'
            order by key
            """
        )
        confirmation_audit_rows = self._connection.fetch_all(
            """
            select raw_payload
            from app.bank_transaction_category_confirmations
            order by confirmed_at, id
            """
        )
        categories = {str(row.get("key")): row_payload(row, "raw_payload") for row in rows}
        for row in confirmation_rows:
            transaction_id = text(row.get("key"))
            category_code = text(row.get("category_code"))
            if not transaction_id or not category_code:
                continue
            payload = row_payload(row, "raw_payload")
            normalized_payload = dict(payload) if isinstance(payload, dict) else {}
            normalized_payload.update(
                {
                    "transaction_id": transaction_id,
                    "category_code": category_code,
                    "source": "auto_confirmation",
                    "updated_by": text(row.get("confirmed_by")) or normalized_payload.get("updated_by") or "",
                    "updated_at": (
                        row.get("confirmed_at").isoformat()
                        if hasattr(row.get("confirmed_at"), "isoformat")
                        else text(row.get("confirmed_at")) or normalized_payload.get("updated_at") or ""
                    ),
                    "version": int_value(row.get("version"), int_value(normalized_payload.get("version"), 1)),
                    "candidate_category_codes": text_list(
                        row.get("candidate_category_codes") or normalized_payload.get("candidate_category_codes")
                    ),
                    "rule_version": text(row.get("rule_version")) or normalized_payload.get("rule_version") or "",
                }
            )
            categories[transaction_id] = normalized_payload
        return normalize_bank_transaction_categories(
            categories,
            [
                payload
                for source_rows in (event_rows, confirmation_audit_rows)
                for row in source_rows
                if isinstance((payload := row_payload(row, "raw_payload")), dict)
            ],
        )

    def save_bank_transaction_categories(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            categories = snapshot.get("categories") if isinstance(snapshot, dict) else None
            for transaction_id, payload in iter_mapping(categories):
                source = text(payload.get("source"))
                if source == "auto_confirmation":
                    self._save_bank_transaction_category_confirmation(connection, transaction_id, payload)
                    continue
                if source == "auto_confirmation_revoked":
                    self._revoke_bank_transaction_category_confirmation(connection, transaction_id, payload)
                    continue
                connection.execute(
                    """
                    delete from app.bank_transaction_category_events
                    where category_id in (
                        select id from app.bank_transaction_categories where legacy_transaction_id = %s
                    )
                    """,
                    (transaction_id,),
                )
                connection.execute(
                    "delete from app.bank_transaction_categories where legacy_transaction_id = %s",
                    (transaction_id,),
                )
                connection.execute(
                    """
                    insert into app.bank_transaction_categories(
                        legacy_transaction_id, category, source, confidence, status, version, updated_by, raw_payload
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        transaction_id,
                        text(payload.get("category_code") or payload.get("category") or "unknown"),
                        text(payload.get("source") or "manual"),
                        decimal_text(payload.get("confidence")),
                        text(payload.get("status") or "active"),
                        int_value(payload.get("version"), 1),
                        text(payload.get("updated_by") or payload.get("actor_id") or payload.get("updated_by_actor")),
                        jsonb(
                            {
                                "normalized_payload": {
                                    **payload,
                                    "category_code": text(payload.get("category_code") or payload.get("category") or "unknown"),
                                    "category_label": text(payload.get("category_label") or payload.get("label") or payload.get("category_code") or payload.get("category")),
                                }
                            }
                        ),
                    ),
                )
            self._replace_bank_transaction_category_events(
                connection,
                snapshot.get("audit_log") if isinstance(snapshot, dict) else None,
            )

        run_in_transaction(self._connection, write)

    def _save_bank_transaction_category_confirmation(
        self,
        connection: Any,
        transaction_id: str,
        payload: dict[str, Any],
    ) -> None:
        category_code = text(payload.get("category_code") or payload.get("category"))
        if not category_code:
            return
        actor = text(payload.get("updated_by") or payload.get("actor_id") or payload.get("confirmed_by")) or ""
        rule_version = text(payload.get("rule_version") or payload.get("category_rule_version")) or ""
        candidate_codes = text_list(payload.get("candidate_category_codes"))
        version = int_value(payload.get("version"), 1)
        existing = connection.fetch_one(
            """
            select id, category_code, candidate_category_codes, rule_version
            from app.bank_transaction_category_confirmations
            where tenant_id = 'default'
              and legacy_transaction_id = %s
              and status = 'active'
            order by confirmed_at desc
            limit 1
            """,
            (transaction_id,),
        )
        raw_payload = {
            "normalized_payload": {
                **payload,
                "transaction_id": transaction_id,
                "category_code": category_code,
                "source": "auto_confirmation",
                "candidate_category_codes": candidate_codes,
                "rule_version": rule_version,
            }
        }
        if (
            isinstance(existing, dict)
            and text(existing.get("category_code")) == category_code
            and text_list(existing.get("candidate_category_codes")) == candidate_codes
            and (text(existing.get("rule_version")) or "") == rule_version
        ):
            connection.execute(
                """
                update app.bank_transaction_category_confirmations
                set version = greatest(version, %s),
                    confirmed_by = %s,
                    raw_payload = %s
                where id = %s
                """,
                (version, actor, jsonb(raw_payload), existing.get("id")),
            )
            return
        connection.execute(
            """
            update app.bank_transaction_category_confirmations
            set status = 'revoked',
                revoked_by = %s,
                revoked_at = now(),
                version = version + 1
            where tenant_id = 'default'
              and legacy_transaction_id = %s
              and status = 'active'
            """,
            (actor, transaction_id),
        )
        connection.execute(
            """
            insert into app.bank_transaction_category_confirmations(
                tenant_id, legacy_transaction_id, category_code, candidate_category_codes,
                rule_version, status, version, confirmed_by, raw_payload
            )
            values ('default', %s, %s, %s, %s, 'active', %s, %s, %s)
            """,
            (
                transaction_id,
                category_code,
                jsonb(candidate_codes),
                rule_version,
                version,
                actor,
                jsonb(raw_payload),
            ),
        )

    def _revoke_bank_transaction_category_confirmation(
        self,
        connection: Any,
        transaction_id: str,
        payload: dict[str, Any],
    ) -> None:
        actor = text(payload.get("updated_by") or payload.get("actor_id") or payload.get("revoked_by")) or ""
        raw_payload = {
            "normalized_payload": {
                **payload,
                "transaction_id": transaction_id,
                "source": "auto_confirmation_revoked",
            }
        }
        connection.execute(
            """
            update app.bank_transaction_category_confirmations
            set status = 'revoked',
                revoked_by = %s,
                revoked_at = now(),
                version = version + 1,
                raw_payload = %s
            where tenant_id = 'default'
              and legacy_transaction_id = %s
              and status = 'active'
            """,
            (actor, jsonb(raw_payload), transaction_id),
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
                        jsonb(snapshot.get("audit_log") if isinstance(snapshot.get("audit_log"), list) else []),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            self._replace_turnover_relation_events(
                connection,
                snapshot.get("audit_log") if isinstance(snapshot, dict) else None,
            )

        run_in_transaction(self._connection, write)

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
        for row_id, payload in iter_mapping(payload_map):
            if changed_ids is not None and row_id not in changed_ids:
                continue
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
                    row_id,
                    row_id,
                    text(payload.get("row_type") or payload.get("type") or "unknown"),
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
            select row_id as key, raw_payload
            from app.workbench_row_overrides
            order by row_id
            """
        )
        if not rows:
            return {}
        row_overrides = {str(row.get("key")): row_payload(row, "raw_payload") for row in rows}
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
        rows = self._connection.fetch_all("select case_id as key, raw_payload from app.workbench_exception_cases order by case_id")
        if not rows:
            return {}
        return {"cases": {str(row.get("key")): row_payload(row, "raw_payload") for row in rows}}

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

    def _replace_bank_transaction_category_events(self, connection: Any, audit_log: Any) -> None:
        if not isinstance(audit_log, list):
            return
        transaction_ids = {text(item.get("transaction_id")) for item in audit_log if isinstance(item, dict)}
        for transaction_id in sorted(item for item in transaction_ids if item):
            connection.execute(
                """
                delete from app.bank_transaction_category_events
                where category_id in (
                    select id from app.bank_transaction_categories where legacy_transaction_id = %s
                )
                """,
                (transaction_id,),
            )
        for item in audit_log:
            if not isinstance(item, dict):
                continue
            transaction_id = text(item.get("transaction_id"))
            if not transaction_id:
                continue
            connection.execute(
                """
                insert into app.bank_transaction_category_events(
                    id, category_id, event_type, actor_id, occurred_at, payload, raw_payload
                )
                values (
                    %s::uuid,
                    (select id from app.bank_transaction_categories where legacy_transaction_id = %s order by updated_at desc limit 1),
                    %s, %s, coalesce(%s::timestamptz, now()), %s, %s
                )
                on conflict (id) do update set payload = excluded.payload, raw_payload = excluded.raw_payload
                """,
                (
                    event_uuid("bank_transaction_category_events", transaction_id, item),
                    transaction_id,
                    text(item.get("event_type") or item.get("operation") or "category_updated"),
                    text(item.get("updated_by") or item.get("actor_id")),
                    text(item.get("updated_at") or item.get("created_at")),
                    jsonb(item),
                    jsonb({"normalized_payload": item}),
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
