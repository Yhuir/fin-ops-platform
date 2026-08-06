from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from typing import Any, Iterator

from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    int_value,
    iter_mapping,
    jsonb,
    load_keyed_rows,
    max_numeric_suffix,
    month_start,
    row_payload,
    run_in_transaction,
    serialize_value,
    text,
    text_list,
    without_keys,
)
from fin_ops_platform.services.postgres_repositories.oa_attachment_identity_bridge import (
    reconcile_oa_attachment_cache_identity_sources,
)
from fin_ops_platform.services.postgres_snapshot_contracts import normalize_app_health_alerts
from fin_ops_platform.services.postgres_connection import PostgresTransaction
from fin_ops_platform.services.state_store_protocol import (
    PROTECTED_ADMIN_USERNAME,
    SETTINGS_ACCESS_CONTROL_KEYS,
    SettingsAccessControlCommitOutcomeUnknown,
    SettingsAccessControlVersionConflict,
    default_settings_access_control,
    settings_access_control_from_payload,
)


OA_SYNC_STATE_KEY = "oa_sync_state"
APP_SETTINGS_KEY = "app_settings"
SETTINGS_ACL_ADVISORY_LOCK_KEY = "fin_ops.app_settings.acl"


class _PostgresSettingsAccessControlCriticalSection:
    def __init__(
        self,
        repository: "PostgresOpsTaxEtcRepository",
        raw_connection: Any,
        executor: Any,
        current: dict[str, Any],
    ) -> None:
        self._repository = repository
        self._raw_connection = raw_connection
        self._executor = executor
        self._current = serialize_value(current)
        self._committed = False

    @property
    def locked_current(self) -> dict[str, Any]:
        return settings_access_control_from_payload(self._current)

    @property
    def committed(self) -> bool:
        return self._committed

    def commit(
        self,
        next_access_control: dict[str, Any],
        durable_audit: dict[str, Any],
    ) -> dict[str, Any]:
        if self._committed:
            raise RuntimeError("Settings access-control critical section was already committed.")
        result = self._repository._commit_settings_acl(
            raw_connection=self._raw_connection,
            executor=self._executor,
            current=self._current,
            next_access_control=next_access_control,
            durable_audit=durable_audit,
        )
        self._current = {**self._current, **result}
        self._committed = True
        return result


@contextmanager
def _repeatable_read_only_snapshot(connection: Any) -> Iterator[Any]:
    transaction_factory = getattr(connection, "transaction", None)
    if not callable(transaction_factory):
        yield connection
        return
    with transaction_factory() as snapshot_connection:
        snapshot_connection.execute("set transaction isolation level repeatable read read only")
        yield snapshot_connection


def _oa_attachment_cache_source_rows(cache_key: str, payload: dict[str, Any]) -> list[dict[str, str | None]]:
    rows: dict[tuple[str, str], dict[str, str | None]] = {}

    def add(kind: str, item: Any) -> None:
        if not isinstance(item, dict):
            return
        source_attachment_key = text(item.get("source_attachment_key"))
        if not source_attachment_key:
            return
        rows[(source_attachment_key, kind)] = {
            "source_attachment_key": source_attachment_key,
            "source_kind": kind,
            "source_expense_item_id": text(item.get("source_expense_item_id")),
            "source_expense_row_index": text(item.get("source_expense_row_index")),
            "source_attachment_name": text(
                item.get("source_attachment_name")
                or item.get("attachment_name")
                or item.get("fileName")
                or item.get("filename")
            ),
        }

    add("cache_key", {"source_attachment_key": cache_key, **dict(payload)})
    for invoice in list(payload.get("invoices") or []):
        add("invoice", invoice)
    for evidence in list(payload.get("evidences") or []):
        add("evidence", evidence)
    artifacts = payload.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            add("artifact", artifact)
    elif isinstance(artifacts, dict):
        add("artifact", artifacts)
    return list(rows.values())


class PostgresOpsTaxEtcRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_settings(self, settings_key: str) -> dict[str, Any]:
        row = self._connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s",
            (settings_key,),
        )
        payload = row_payload(row, "settings_payload")
        return dict(payload) if isinstance(payload, dict) else {}

    def save_settings(self, settings_key: str, payload: dict[str, Any]) -> None:
        if settings_key == APP_SETTINGS_KEY:
            self._save_app_settings(payload)
            return
        self._save_settings_with_executor(self._connection, settings_key, payload)

    def save_settings_in_transaction(self, settings_key: str, payload: dict[str, Any], *, transaction: Any) -> None:
        if settings_key == APP_SETTINGS_KEY:
            self._save_app_settings_in_transaction(payload, transaction=transaction)
            return
        self._save_settings_with_executor(transaction, settings_key, payload)

    def save_app_settings_in_transaction(self, payload: dict[str, Any], *, transaction: Any) -> None:
        self.save_settings_in_transaction("app_settings", payload, transaction=transaction)

    def save_app_settings_for_bank_flow_rule_version_in_transaction(
        self,
        payload: dict[str, Any],
        *,
        expected_version: int,
        transaction: Any,
    ) -> dict[str, Any] | None:
        transaction.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (SETTINGS_ACL_ADVISORY_LOCK_KEY,),
        )
        row = transaction.fetch_one(
            """
            select settings_payload
            from app.app_settings
            where settings_key = %s
            for update
            """,
            (APP_SETTINGS_KEY,),
        )
        current_payload = row_payload(row, "settings_payload") if row is not None else {}
        current_payload = {
            **default_settings_access_control(),
            **(current_payload if isinstance(current_payload, dict) else {}),
            **settings_access_control_from_payload(current_payload),
        }
        current_rules = (
            current_payload.get("bank_flow_rule_batch_tag_rules")
            if isinstance(current_payload, dict)
            else None
        )
        current_version = int_value(
            current_rules.get("version") if isinstance(current_rules, dict) else 1,
            1,
        )
        if current_version != int(expected_version):
            return None
        next_rules = payload.get("bank_flow_rule_batch_tag_rules")
        if not isinstance(next_rules, dict):
            raise ValueError("bank_flow_rule_batch_tag_rules payload is required.")
        persisted_payload = {
            **current_payload,
            "bank_flow_rule_batch_tag_rules": dict(next_rules),
        }
        self._save_settings_with_executor(transaction, APP_SETTINGS_KEY, persisted_payload)
        return persisted_payload

    def save_app_settings_for_batch_accounting_tag_selection_version_in_transaction(
        self,
        payload: dict[str, Any],
        *,
        expected_version: int,
        transaction: Any,
    ) -> dict[str, Any] | None:
        return self.save_app_settings_for_versioned_family_in_transaction(
            payload,
            family_key="batch_accounting_tag_selection",
            expected_version=expected_version,
            transaction=transaction,
        )

    def save_app_settings_for_versioned_family_in_transaction(
        self,
        payload: dict[str, Any],
        *,
        family_key: str,
        expected_version: int,
        transaction: Any,
    ) -> dict[str, Any] | None:
        transaction.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (SETTINGS_ACL_ADVISORY_LOCK_KEY,),
        )
        row = transaction.fetch_one(
            """
            select settings_payload
            from app.app_settings
            where settings_key = %s
            for update
            """,
            (APP_SETTINGS_KEY,),
        )
        current_payload = row_payload(row, "settings_payload") if row is not None else {}
        current_payload = {
            **default_settings_access_control(),
            **(current_payload if isinstance(current_payload, dict) else {}),
            **settings_access_control_from_payload(current_payload),
        }
        current_family = current_payload.get(family_key)
        current_version = int_value(
            current_family.get("version") if isinstance(current_family, dict) else 1,
            1,
        )
        if current_version != int(expected_version):
            return None
        next_family = payload.get(family_key)
        if not isinstance(next_family, dict):
            raise ValueError(f"{family_key} payload is required.")
        persisted_payload = {**current_payload, family_key: dict(next_family)}
        self._save_settings_with_executor(transaction, APP_SETTINGS_KEY, persisted_payload)
        return persisted_payload

    def _save_app_settings(self, payload: dict[str, Any]) -> None:
        connection_factory = getattr(self._connection, "connection", None)
        if not callable(connection_factory):
            run_in_transaction(
                self._connection,
                lambda transaction: self._save_app_settings_in_transaction(payload, transaction=transaction),
            )
            return
        with connection_factory() as raw_connection:
            executor = PostgresTransaction(raw_connection)
            lock_acquired = False
            try:
                executor.execute(
                    "select pg_advisory_lock(hashtextextended(%s, 0))",
                    (SETTINGS_ACL_ADVISORY_LOCK_KEY,),
                )
                raw_connection.commit()
                lock_acquired = True
                executor.execute("begin")
                self._save_app_settings_in_transaction(
                    payload,
                    transaction=executor,
                    advisory_lock_already_held=True,
                )
                raw_connection.commit()
            except Exception:
                raw_connection.rollback()
                raise
            finally:
                if lock_acquired:
                    self._release_settings_acl_session_lock(raw_connection, executor)

    def _save_app_settings_in_transaction(
        self,
        payload: dict[str, Any],
        *,
        transaction: Any,
        advisory_lock_already_held: bool = False,
    ) -> None:
        if not advisory_lock_already_held:
            transaction.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
                (SETTINGS_ACL_ADVISORY_LOCK_KEY,),
            )
        row = transaction.fetch_one(
            """
            select settings_payload
            from app.app_settings
            where settings_key = %s
            for update
            """,
            (APP_SETTINGS_KEY,),
        )
        current = row_payload(row, "settings_payload") if row is not None else {}
        current = current if isinstance(current, dict) else {}
        incoming_non_acl = {
            key: value for key, value in serialize_value(payload).items() if key not in SETTINGS_ACCESS_CONTROL_KEYS
        }
        persisted = {
            **current,
            **incoming_non_acl,
            **settings_access_control_from_payload(current),
        }
        self._save_settings_with_executor(transaction, APP_SETTINGS_KEY, persisted)

    @contextmanager
    def begin_settings_acl_critical_section(self, expected_version: int) -> Iterator[Any]:
        connection_factory = getattr(self._connection, "connection", None)
        if not callable(connection_factory):
            raise RuntimeError("PostgreSQL ACL critical sections require a connection context factory.")
        with connection_factory() as raw_connection:
            executor = PostgresTransaction(raw_connection)
            lock_acquired = False
            critical_section: _PostgresSettingsAccessControlCriticalSection | None = None
            try:
                executor.execute(
                    "select pg_advisory_lock(hashtextextended(%s, 0))",
                    (SETTINGS_ACL_ADVISORY_LOCK_KEY,),
                )
                raw_connection.commit()
                lock_acquired = True
                executor.execute("begin")
                row = executor.fetch_one(
                    """
                    select settings_payload
                    from app.app_settings
                    where settings_key = %s
                    for update
                    """,
                    (APP_SETTINGS_KEY,),
                )
                current = row_payload(row, "settings_payload") if row is not None else {}
                current = {
                    **(current if isinstance(current, dict) else {}),
                    **settings_access_control_from_payload(current),
                }
                current_version = current["access_control_version"]
                if current_version != int(expected_version):
                    raw_connection.rollback()
                    raise SettingsAccessControlVersionConflict(current_version)
                critical_section = _PostgresSettingsAccessControlCriticalSection(
                    self,
                    raw_connection,
                    executor,
                    current,
                )
                yield critical_section
            finally:
                if critical_section is None or not critical_section.committed:
                    try:
                        raw_connection.rollback()
                    except Exception:
                        pass
                if lock_acquired:
                    self._release_settings_acl_session_lock(raw_connection, executor)

    def _commit_settings_acl(
        self,
        *,
        raw_connection: Any,
        executor: Any,
        current: dict[str, Any],
        next_access_control: dict[str, Any],
        durable_audit: dict[str, Any],
    ) -> dict[str, Any]:
        mutation_id = str(durable_audit.get("mutation_id") or "").strip()
        if not mutation_id:
            raise ValueError("Settings access-control audit mutation_id is required.")
        current_acl = settings_access_control_from_payload(current)
        candidate = settings_access_control_from_payload(next_access_control)
        candidate["access_control_version"] = current_acl["access_control_version"] + 1
        if candidate["admin_usernames"] != [PROTECTED_ADMIN_USERNAME]:
            raise ValueError("The protected administrator is immutable.")
        persisted = {**current, **candidate}
        audit_payload = {
            **serialize_value(durable_audit),
            "before_version": current_acl["access_control_version"],
            "after_version": candidate["access_control_version"],
        }
        try:
            self._save_settings_with_executor(executor, APP_SETTINGS_KEY, persisted)
            executor.execute(
                """
                insert into audit.events(
                    event_type, object_type, object_id, actor_id, actor_name, scope, trace_id,
                    payload, raw_payload
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "settings.access_control.updated",
                    "app_settings",
                    APP_SETTINGS_KEY,
                    str(durable_audit.get("actor_id") or "system"),
                    str(durable_audit.get("actor_name") or ""),
                    "access_control",
                    str(durable_audit.get("request_id") or mutation_id),
                    jsonb(audit_payload),
                    jsonb({"normalized_payload": audit_payload}),
                ),
            )
        except Exception:
            raw_connection.rollback()
            raise
        try:
            raw_connection.commit()
        except Exception as exc:
            raise SettingsAccessControlCommitOutcomeUnknown(mutation_id) from exc
        return candidate

    def recover_settings_acl_commit(self, mutation_id: str) -> dict[str, Any]:
        normalized_mutation_id = str(mutation_id or "").strip()
        if not normalized_mutation_id:
            raise ValueError("Settings access-control mutation_id is required.")
        connection_factory = getattr(self._connection, "connection", None)
        if not callable(connection_factory):
            raise RuntimeError("PostgreSQL ACL commit recovery requires a connection context factory.")
        with connection_factory() as raw_connection:
            executor = PostgresTransaction(raw_connection)
            lock_acquired = False
            try:
                executor.execute(
                    "select pg_advisory_lock(hashtextextended(%s, 0))",
                    (SETTINGS_ACL_ADVISORY_LOCK_KEY,),
                )
                raw_connection.commit()
                lock_acquired = True
                executor.execute("begin")
                row = executor.fetch_one(
                    "select settings_payload from app.app_settings where settings_key = %s",
                    (APP_SETTINGS_KEY,),
                )
                audit_row = executor.fetch_one(
                    """
                    select 1 as audit_present
                    from audit.events
                    where event_type = 'settings.access_control.updated'
                      and payload @> %s
                    limit 1
                    """,
                    (jsonb({"mutation_id": normalized_mutation_id}),),
                )
                raw_connection.commit()
                current = row_payload(row, "settings_payload") if row is not None else {}
                return {
                    "access_control": settings_access_control_from_payload(current),
                    "audit_present": audit_row is not None,
                }
            finally:
                if lock_acquired:
                    self._release_settings_acl_session_lock(raw_connection, executor)

    @staticmethod
    def _release_settings_acl_session_lock(raw_connection: Any, executor: Any) -> None:
        try:
            raw_connection.rollback()
            executor.execute(
                "select pg_advisory_unlock(hashtextextended(%s, 0))",
                (SETTINGS_ACL_ADVISORY_LOCK_KEY,),
            )
            raw_connection.commit()
        except Exception:
            try:
                raw_connection.rollback()
            except Exception:
                pass

    def _save_settings_with_executor(self, executor: Any, settings_key: str, payload: dict[str, Any]) -> None:
        normalized = serialize_value(payload)
        executor.execute(
            """
            insert into app.app_settings(settings_key, version, settings_payload, raw_payload, updated_at)
            values (%s, 1, %s, %s, now())
            on conflict (settings_key) do update set
                version = app.app_settings.version + 1,
                settings_payload = excluded.settings_payload,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (settings_key, jsonb(normalized), jsonb({"normalized_payload": normalized})),
        )

    def load_pending_invoice_commands(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            """
            select command_id, command_payload, raw_payload
            from app.pending_invoice_manual_invoice_commands
            order by created_at, command_id
            """
        )
        commands: dict[str, Any] = {}
        for row in rows:
            payload = row_payload(row, "command_payload", "raw_payload")
            if not isinstance(payload, dict):
                continue
            command_id = text(payload.get("request_id") or payload.get("command_id") or row.get("command_id"))
            if command_id:
                commands[command_id] = payload
        return commands

    def save_pending_invoice_commands(self, snapshot: dict[str, Any]) -> None:
        normalized = serialize_value(snapshot)
        if not isinstance(normalized, dict):
            normalized = {}

        def write(connection: Any) -> None:
            command_ids: list[str] = []
            for legacy_key, payload in iter_mapping(normalized):
                command_id = text(payload.get("request_id") or payload.get("command_id") or payload.get("id") or legacy_key)
                if not command_id:
                    continue
                request_id = text(payload.get("request_id") or command_id)
                command_ids.append(command_id)
                connection.execute(
                    """
                    insert into app.pending_invoice_manual_invoice_commands(
                        legacy_mongo_id, command_id, request_id, request_key, status,
                        invoice_id, relation_case_id, actor_id, error_code, error_message,
                        last_successful_status, attempt_count, status_history,
                        result_payload, command_payload, raw_payload, created_at, updated_at
                    )
                    values (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        coalesce(%s::timestamptz, now()), coalesce(%s::timestamptz, now())
                    )
                    on conflict (command_id) do update set
                        legacy_mongo_id = excluded.legacy_mongo_id,
                        request_id = excluded.request_id,
                        request_key = excluded.request_key,
                        status = excluded.status,
                        invoice_id = excluded.invoice_id,
                        relation_case_id = excluded.relation_case_id,
                        actor_id = excluded.actor_id,
                        error_code = excluded.error_code,
                        error_message = excluded.error_message,
                        last_successful_status = excluded.last_successful_status,
                        attempt_count = excluded.attempt_count,
                        status_history = excluded.status_history,
                        result_payload = excluded.result_payload,
                        command_payload = excluded.command_payload,
                        raw_payload = excluded.raw_payload,
                        created_at = excluded.created_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        text(payload.get("legacy_mongo_id") or legacy_key),
                        command_id,
                        request_id,
                        text(payload.get("request_key")),
                        text(payload.get("status") or "unknown"),
                        text(payload.get("invoice_id")),
                        text(payload.get("relation_case_id") or payload.get("case_id")),
                        text(payload.get("actor_id") or payload.get("actor")),
                        text(payload.get("error_code")),
                        text(payload.get("error") or payload.get("error_message") or payload.get("last_error")),
                        text(payload.get("last_successful_status")),
                        int_value(payload.get("attempt_count"), 0),
                        text_list(payload.get("status_history")),
                        jsonb(payload.get("result") if isinstance(payload.get("result"), dict) else {}),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                        text(payload.get("created_at")),
                        text(payload.get("updated_at")),
                    ),
                )
            if command_ids:
                connection.execute(
                    "delete from app.pending_invoice_manual_invoice_commands where not (command_id = any(%s))",
                    (command_ids,),
                )
            else:
                connection.execute("delete from app.pending_invoice_manual_invoice_commands")

        run_in_transaction(self._connection, write)

    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None:
        normalized_key = str(cache_key or "").strip()
        if not normalized_key:
            return None
        row = self._connection.fetch_one(
            """
            select normalized_payload
            from app.oa_attachment_invoice_cache
            where source_attachment_key = %s
            """,
            (normalized_key,),
        )
        payload = row_payload(row, "normalized_payload")
        return dict(payload) if isinstance(payload, dict) else None

    def save_oa_attachment_invoice_cache_entry(self, cache_key: str, payload: dict[str, object]) -> None:
        normalized_key = str(cache_key or "").strip()
        if not normalized_key:
            raise ValueError("OA attachment cache key is required.")
        normalized_payload = serialize_value({**dict(payload), "cache_key": normalized_key})

        def write(connection: Any) -> None:
            connection.execute(
                """
                insert into app.oa_attachment_invoice_cache(
                    source_attachment_key, parser_version, cache_schema_version, parsed_at,
                    evidences, invoices, artifacts, normalized_payload, raw_payload
                )
                values (%s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s)
                on conflict (source_attachment_key) do update set
                    parser_version = excluded.parser_version,
                    cache_schema_version = excluded.cache_schema_version,
                    parsed_at = excluded.parsed_at,
                    evidences = excluded.evidences,
                    invoices = excluded.invoices,
                    artifacts = excluded.artifacts,
                    normalized_payload = excluded.normalized_payload,
                    raw_payload = excluded.raw_payload
                """,
                (
                    normalized_key,
                    str(normalized_payload.get("parser_version") or "unknown"),
                    str(normalized_payload.get("cache_schema_version") or "unknown"),
                    normalized_payload.get("parsed_at"),
                    jsonb(normalized_payload.get("evidences") or []),
                    jsonb(normalized_payload.get("invoices") or []),
                    jsonb(normalized_payload.get("artifacts") or {}),
                    jsonb(normalized_payload),
                    jsonb({"normalized_payload": normalized_payload}),
                ),
            )
            connection.execute(
                "delete from app.oa_attachment_invoice_cache_sources where cache_source_attachment_key = %s",
                (normalized_key,),
            )
            for source in _oa_attachment_cache_source_rows(normalized_key, normalized_payload):
                connection.execute(
                    """
                    insert into app.oa_attachment_invoice_cache_sources(
                        cache_source_attachment_key, source_attachment_key, source_kind,
                        source_expense_item_id, source_expense_row_index, source_attachment_name, updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, now())
                    on conflict (cache_source_attachment_key, source_attachment_key, source_kind) do update set
                        source_expense_item_id = excluded.source_expense_item_id,
                        source_expense_row_index = excluded.source_expense_row_index,
                        source_attachment_name = excluded.source_attachment_name,
                        updated_at = now()
                    """,
                    (
                        normalized_key,
                        source["source_attachment_key"],
                        source["source_kind"],
                        source["source_expense_item_id"],
                        source["source_expense_row_index"],
                        source["source_attachment_name"],
                    ),
                )
            reconcile_oa_attachment_cache_identity_sources(
                connection,
                cache_source_attachment_keys=[normalized_key],
            )

        run_in_transaction(self._connection, write)

    def clear_oa_attachment_invoice_cache(self) -> int:
        return self._connection.execute("delete from app.oa_attachment_invoice_cache")

    def load_oa_sync_state(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            """
            select sync_key, payload, raw_payload
            from app.oa_sync_watermarks
            order by sync_key
            """
        )
        payloads = {str(row.get("sync_key")): row_payload(row, "payload", "raw_payload") for row in rows}
        state_payload = payloads.get(OA_SYNC_STATE_KEY)
        return dict(state_payload) if isinstance(state_payload, dict) else payloads

    def save_oa_sync_state(self, snapshot: dict[str, Any]) -> None:
        normalized = serialize_value(snapshot)
        if not isinstance(normalized, dict):
            normalized = {}
        self._connection.execute(
            """
            insert into app.oa_sync_watermarks(sync_key, status, payload, raw_payload)
            values (%s, 'active', %s, %s)
            on conflict (sync_key) do update set
                status = excluded.status,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                version = app.oa_sync_watermarks.version + 1,
                updated_at = now()
            """,
            (
                OA_SYNC_STATE_KEY,
                jsonb(normalized),
                jsonb({"normalized_payload": normalized}),
            ),
        )

    def load_manual_oa_imports(self) -> dict[str, object]:
        rows = self._connection.fetch_all(
            """
            select row_id, source, actor_id, imported_at, audit_payload, raw_payload
            from app.manual_oa_imports
            where status = 'active'
            order by row_id
            """
        )
        if not rows:
            return {}
        payload: dict[str, object] = {"row_ids": [], "entries": {}, "audit_log": []}
        row_ids = payload["row_ids"]
        entries = payload["entries"]
        assert isinstance(row_ids, list)
        assert isinstance(entries, dict)
        for row in rows:
            row_id = str(row.get("row_id") or "").strip()
            if not row_id:
                continue
            entry = row_payload(row, "raw_payload")
            if not isinstance(entry, dict):
                entry = {}
            entry = {**entry, "row_id": row_id, "source": row.get("source") or "manual_oa_import"}
            row_ids.append(row_id)
            entries[row_id] = entry
        return payload

    def save_manual_oa_imports(self, payload: dict[str, object]) -> None:
        raw_entries = payload.get("entries") if isinstance(payload, dict) else None
        entries = {
            str(row_id).strip(): dict(entry) if isinstance(entry, dict) else {"row_id": str(row_id).strip()}
            for row_id, entry in iter_mapping(raw_entries)
            if str(row_id).strip()
        }

        def write(connection: Any) -> None:
            active_row_ids = sorted(entries)
            if active_row_ids:
                connection.execute(
                    "update app.manual_oa_imports set status = 'inactive' where row_id <> all(%s)",
                    (active_row_ids,),
                )
            else:
                connection.execute("update app.manual_oa_imports set status = 'inactive'")
            for row_id, entry in entries.items():
                normalized = {**entry, "row_id": row_id}
                audit_payload = normalized.get("audit") if isinstance(normalized.get("audit"), dict) else {}
                connection.execute(
                    """
                    insert into app.manual_oa_imports(
                        row_id, source, actor_id, imported_at, status, audit_payload, raw_payload
                    )
                    values (%s, %s, %s, coalesce(%s::timestamptz, now()), 'active', %s, %s)
                    on conflict (row_id) do update set
                        source = excluded.source,
                        actor_id = excluded.actor_id,
                        imported_at = excluded.imported_at,
                        status = 'active',
                        audit_payload = excluded.audit_payload,
                        raw_payload = excluded.raw_payload
                    """,
                    (
                        row_id,
                        text(normalized.get("source") or "manual_oa_import"),
                        text(normalized.get("actor_id")),
                        text(normalized.get("imported_at")),
                        jsonb(audit_payload),
                        jsonb({"normalized_payload": normalized}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def load_tax_certified_imports(self) -> dict[str, Any]:
        sessions = load_keyed_rows(
            self._connection,
            "select session_id as key, raw_payload from app.tax_certified_import_sessions order by imported_at, session_id",
        )
        batches = load_keyed_rows(
            self._connection,
            "select batch_id as key, raw_payload from app.tax_certified_import_batches order by created_at, batch_id",
        )
        records = load_keyed_rows(
            self._connection,
            "select certified_unique_key as key, raw_payload from app.tax_certified_import_records order by scope_month, certified_unique_key",
        )
        if not (sessions or batches or records):
            return {}
        return {
            "session_counter": max_numeric_suffix(sessions),
            "file_counter": 0,
            "batch_counter": max_numeric_suffix(batches),
            "sessions": sessions,
            "batches": batches,
            "records": records,
        }

    def save_tax_certified_imports(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            normalized = serialize_value(snapshot)
            sessions = normalized.get("sessions") if isinstance(normalized, dict) else None
            for session_id, payload in iter_mapping(sessions):
                record_count = sum(
                    len(file_payload.get("rows") or [])
                    for file_payload in payload.get("files", [])
                    if isinstance(file_payload, dict)
                )
                months = [
                    str(file_payload.get("month"))
                    for file_payload in payload.get("files", [])
                    if isinstance(file_payload, dict) and file_payload.get("month")
                ]
                connection.execute(
                    """
                    insert into app.tax_certified_import_sessions(
                        legacy_mongo_id, session_id, status, scope_month, imported_by,
                        imported_at, record_count, raw_payload
                    )
                    values (%s, %s, %s, %s::date, %s, coalesce(%s::timestamptz, now()), %s, %s)
                    on conflict (session_id) do update set
                        status = excluded.status,
                        scope_month = excluded.scope_month,
                        imported_by = excluded.imported_by,
                        imported_at = excluded.imported_at,
                        record_count = excluded.record_count,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        session_id,
                        session_id,
                        text(payload.get("status") or "unknown"),
                        month_start(months[0]) if months else None,
                        text(payload.get("imported_by")),
                        text(payload.get("created_at") or payload.get("imported_at")),
                        record_count,
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            batches = normalized.get("batches") if isinstance(normalized, dict) else None
            for batch_id, payload in iter_mapping(batches):
                connection.execute(
                    """
                    insert into app.tax_certified_import_batches(
                        legacy_mongo_id, batch_id, session_id, status, scope_month, row_count, raw_payload
                    )
                    values (
                        %s, %s,
                        (select id from app.tax_certified_import_sessions where session_id = %s limit 1),
                        %s, %s::date, %s, %s
                    )
                    on conflict (batch_id) do update set
                        session_id = excluded.session_id,
                        status = excluded.status,
                        scope_month = excluded.scope_month,
                        row_count = excluded.row_count,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        batch_id,
                        batch_id,
                        text(payload.get("session_id")),
                        text(payload.get("status") or "confirmed"),
                        month_start((payload.get("months") or [None])[0] if isinstance(payload.get("months"), list) else None),
                        int_value(payload.get("persisted_record_count") or payload.get("row_count"), 0),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            records = normalized.get("records") if isinstance(normalized, dict) else None
            for record_key, payload in iter_mapping(records):
                unique_key = text(payload.get("unique_key") or record_key)
                if not unique_key:
                    continue
                connection.execute(
                    """
                    insert into app.tax_certified_import_records(
                        legacy_mongo_id, certified_unique_key, invoice_no, invoice_code, digital_invoice_no,
                        seller_name, seller_tax_no, invoice_date, scope_month, amount, tax_amount,
                        batch_id, matched_plan_id, status, raw_payload
                    )
                    values (
                        %s, %s, %s, %s, %s, %s, %s, %s::date, %s::date, %s, %s,
                        (select id from app.tax_certified_import_batches where batch_id = %s limit 1),
                        %s, %s, %s
                    )
                    on conflict (certified_unique_key) do update set
                        invoice_no = excluded.invoice_no,
                        invoice_code = excluded.invoice_code,
                        digital_invoice_no = excluded.digital_invoice_no,
                        seller_name = excluded.seller_name,
                        seller_tax_no = excluded.seller_tax_no,
                        invoice_date = excluded.invoice_date,
                        scope_month = excluded.scope_month,
                        amount = excluded.amount,
                        tax_amount = excluded.tax_amount,
                        batch_id = excluded.batch_id,
                        matched_plan_id = excluded.matched_plan_id,
                        status = excluded.status,
                        raw_payload = excluded.raw_payload
                    """,
                    (
                        text(payload.get("id") or unique_key),
                        unique_key,
                        text(payload.get("invoice_no")),
                        text(payload.get("invoice_code")),
                        text(payload.get("digital_invoice_no")),
                        text(payload.get("seller_name")),
                        text(payload.get("seller_tax_no")),
                        text(payload.get("issue_date") or payload.get("invoice_date")),
                        month_start(payload.get("month") or payload.get("scope_month")),
                        decimal_text(payload.get("amount")),
                        decimal_text(payload.get("tax_amount")) or "0",
                        text(payload.get("batch_id")),
                        text(payload.get("matched_plan_id")),
                        text(payload.get("status") or payload.get("selection_status") or "active"),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def save_tax_offset_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        normalized = serialize_value(plan)
        if not isinstance(normalized, dict):
            raise ValueError("tax offset plan payload must be a dictionary.")
        plan_id = text(normalized.get("id"))
        if not plan_id:
            raise ValueError("tax offset plan id is required.")
        idempotency_key = text(normalized.get("idempotency_key"))
        if idempotency_key:
            existing = self._connection.fetch_one(
                """
                select raw_payload
                from app.tax_offset_plans
                where idempotency_key = %s
                limit 1
                """,
                (idempotency_key,),
            )
            existing_payload = row_payload(existing, "raw_payload")
            if isinstance(existing_payload, dict):
                return dict(existing_payload)
        self._connection.execute(
            """
            insert into app.tax_offset_plans(
                plan_id, scope_month, status, selected_output_ids, selected_input_ids,
                calculation_summary, source_versions, read_model_scope_key,
                created_by, idempotency_key, audit_trace, raw_payload, created_at, updated_at
            )
            values (
                %s, %s::date, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                coalesce(%s::timestamptz, now()), coalesce(%s::timestamptz, now())
            )
            on conflict (plan_id) do update set
                status = excluded.status,
                selected_output_ids = excluded.selected_output_ids,
                selected_input_ids = excluded.selected_input_ids,
                calculation_summary = excluded.calculation_summary,
                source_versions = excluded.source_versions,
                read_model_scope_key = excluded.read_model_scope_key,
                created_by = excluded.created_by,
                audit_trace = excluded.audit_trace,
                raw_payload = excluded.raw_payload,
                updated_at = excluded.updated_at
            """,
            (
                plan_id,
                month_start(normalized.get("month")),
                text(normalized.get("status") or "saved"),
                text_list(normalized.get("selected_output_ids")),
                text_list(normalized.get("selected_input_ids")),
                jsonb(normalized.get("summary") if isinstance(normalized.get("summary"), dict) else {}),
                jsonb(normalized.get("source_versions") if isinstance(normalized.get("source_versions"), dict) else {}),
                text(normalized.get("read_model_scope_key")),
                text(normalized.get("actor_id")),
                idempotency_key,
                jsonb(normalized.get("audit") if isinstance(normalized.get("audit"), dict) else {}),
                jsonb(normalized),
                text(normalized.get("created_at")),
                text(normalized.get("updated_at")),
            ),
        )
        return normalized

    def load_etc_state(self) -> dict[str, Any]:
        current_state_filter = "coalesce(legacy_mongo_id, '') !~ '^current_state:'"
        invoices = load_keyed_rows(
            self._connection,
            f"select etc_invoice_id as key, raw_payload from app.etc_invoices where {current_state_filter} order by created_at, etc_invoice_id",
        )
        import_batches = load_keyed_rows(
            self._connection,
            f"select batch_id as key, raw_payload from app.etc_import_batches where {current_state_filter} order by created_at, batch_id",
        )
        batches = load_keyed_rows(
            self._connection,
            f"select submission_batch_id as key, raw_payload from app.etc_submission_batches where {current_state_filter} order by created_at, submission_batch_id",
        )
        business_batches = load_keyed_rows(
            self._connection,
            f"select business_batch_id as key, raw_payload from app.etc_business_batches where {current_state_filter} order by created_at, business_batch_id",
        )
        business_batches = {
            business_batch_id: without_keys(payload, {"id"})
            for business_batch_id, payload in business_batches.items()
        }
        if not (invoices or import_batches or batches or business_batches):
            return {}
        return {
            "invoice_counter": max_numeric_suffix(invoices),
            "batch_counter": max_numeric_suffix(batches),
            "import_batch_counter": max_numeric_suffix(import_batches),
            "business_batch_counter": max_numeric_suffix(business_batches),
            "batch_day_counters": {},
            "invoices": invoices,
            "invoice_numbers": {
                str(payload.get("invoice_number")): invoice_id
                for invoice_id, payload in invoices.items()
                if isinstance(payload, dict) and payload.get("invoice_number")
            },
            "batches": batches,
            "import_batches": import_batches,
            "business_batches": business_batches,
        }

    def list_etc_business_batch_summaries(self, **query: Any) -> dict[str, Any]:
        bucket = str(query.get("bucket") or "unsubmitted").strip()
        if bucket not in {"unsubmitted", "staged", "submitted"}:
            raise ValueError("ETC business batch bucket must be unsubmitted, staged, or submitted.")
        page = max(1, int(query.get("page") or 1))
        page_size = max(1, min(500, int(query.get("page_size") or 100)))
        owner_user_ids = [str(value).strip() for value in query.get("owner_user_ids") or [] if str(value).strip()]
        params = (
            bool(query.get("can_admin_access")),
            owner_user_ids,
            text(query.get("owner_org_id")),
            text(query.get("task_id")),
            text(query.get("month")),
            text(query.get("plate")),
            text(query.get("keyword")),
        )
        common_sql = """
            with canonical as (
                select
                    batch.business_batch_id,
                    batch.task_id,
                    batch.status,
                    batch.scope_month,
                    batch.invoice_count,
                    batch.total_amount,
                    batch.created_at,
                    nullif(
                        coalesce(
                            batch.raw_payload->'normalized_payload'->>'oa_draft_id',
                            batch.raw_payload->>'oa_draft_id'
                        ),
                        ''
                    ) as oa_draft_id,
                    coalesce(batch.raw_payload->'normalized_payload', batch.raw_payload) as batch_payload,
                    coalesce(task.raw_payload->'normalized_payload', task.raw_payload) as task_payload
                from app.etc_business_batches batch
                left join app.etc_reconciliation_tasks task on task.task_id = batch.task_id
                where coalesce(batch.legacy_mongo_id, '') !~ '^current_state:'
                  and batch.status not in ('deleted', 'superseded')
            ), scoped as (
                select canonical.*,
                    case
                        when status in ('oa_submitted', 'manually_marked_submitted', 'closed') then 'submitted'
                        when status = 'oa_confirmation_pending' then 'staged'
                        else 'unsubmitted'
                    end as bucket
                from canonical
                where (
                    %s::boolean
                    or (
                        nullif(batch_payload->>'owner_user_id', '') is null
                        and nullif(batch_payload->>'owner_org_id', '') is null
                    )
                    or nullif(batch_payload->>'owner_user_id', '') = any(%s::text[])
                    or nullif(batch_payload->>'owner_org_id', '') = %s::text
                )
                  and (%s::text is null or task_id = %s::text)
                  and (
                    %s::text is null
                    or scope_month = to_date(%s::text, 'YYYY-MM')
                    or (scope_month is null and exists (
                        select 1 from app.etc_invoices invoice
                        where invoice.business_batch_id = canonical.business_batch_id
                          and %s::text in (
                              left(coalesce(invoice.invoice_date::text, ''), 7),
                              left(coalesce(invoice.raw_payload->'normalized_payload'->>'passage_start_date', ''), 7),
                              left(coalesce(invoice.raw_payload->'normalized_payload'->>'passage_end_date', ''), 7)
                          )
                    ))
                  )
                  and (
                    %s::text is null
                    or exists (
                        select 1 from app.etc_invoices invoice
                        where invoice.business_batch_id = canonical.business_batch_id
                          and lower(coalesce(invoice.raw_payload->'normalized_payload'->>'plate_number', '')) like '%%' || lower(%s::text) || '%%'
                    )
                  )
                  and (
                    %s::text is null
                    or lower(coalesce(batch_payload->>'title', '')) like '%%' || lower(%s::text) || '%%'
                    or lower(canonical.business_batch_id) like '%%' || lower(%s::text) || '%%'
                    or lower(coalesce(batch_payload->>'external_etc_batch_id', '')) like '%%' || lower(%s::text) || '%%'
                    or exists (
                        select 1 from app.etc_invoices invoice
                        where invoice.business_batch_id = canonical.business_batch_id
                          and lower(coalesce(invoice.invoice_no, '')) like '%%' || lower(%s::text) || '%%'
                    )
                  )
            )
        """
        repeated_params = (
            params[0], params[1], params[2],
            params[3], params[3],
            params[4], params[4], params[4],
            params[5], params[5],
            params[6], params[6], params[6], params[6], params[6],
        )
        with _repeatable_read_only_snapshot(self._connection) as connection:
            count_rows = connection.fetch_all(
                common_sql
                + """
                , bucket_counts as (
                    select bucket, count(*)::integer as count
                    from scoped
                    group by bucket
                ), invoice_stats as (
                    select
                        count(*)::integer as etc_invoice_count,
                        count(*) filter (where import_batch.batch_id is not null)::integer
                            as imported_invoice_count
                    from app.etc_invoices invoice
                    left join app.etc_import_batches import_batch
                      on import_batch.batch_id = nullif(
                          coalesce(
                              invoice.raw_payload->'normalized_payload'->>'import_batch_id',
                              invoice.raw_payload->>'import_batch_id'
                          ),
                          ''
                      )
                     and coalesce(import_batch.legacy_mongo_id, '') !~ '^current_state:'
                     and import_batch.status <> 'deleted'
                    where coalesce(invoice.legacy_mongo_id, '') !~ '^current_state:'
                      and invoice.status <> 'deleted'
                ), statistics as (
                    select
                        invoice_stats.etc_invoice_count,
                        batch_stats.business_batch_count,
                        batch_stats.unsubmitted_batch_count,
                        batch_stats.draft_batch_count,
                        batch_stats.submitted_batch_count,
                        (
                            select count(*)::integer
                            from app.etc_reconciliation_tasks task
                            where coalesce(task.legacy_mongo_id, '') !~ '^current_state:'
                              and task.status <> 'deleted'
                        ) as reconciliation_task_count,
                        (
                            select count(*)::integer
                            from app.etc_reconciliation_files file
                            where coalesce(file.legacy_mongo_id, '') !~ '^current_state:'
                              and file.status <> 'deleted'
                        ) as source_file_count,
                        invoice_stats.imported_invoice_count,
                        (
                            select count(distinct link.etc_invoice_id)::integer
                            from app.etc_batch_invoice_links link
                            where link.link_status = 'active'
                              and link.tenant_id = 'default'
                        ) as linked_canonical_invoice_count,
                        batch_stats.oa_draft_batch_count
                    from (
                        select
                            count(*)::integer as business_batch_count,
                            count(*) filter (
                                where status not in (
                                    'oa_confirmation_pending', 'oa_submitted', 'manually_marked_submitted', 'closed'
                                )
                            )::integer as unsubmitted_batch_count,
                            count(*) filter (where status = 'oa_confirmation_pending')::integer as draft_batch_count,
                            count(*) filter (
                                where status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                            )::integer as submitted_batch_count,
                            count(*) filter (where oa_draft_id is not null)::integer as oa_draft_batch_count
                        from canonical
                    ) batch_stats
                    cross join invoice_stats
                )
                select bucket.bucket, coalesce(bucket_counts.count, 0)::integer as count, statistics.*
                from (values ('unsubmitted'), ('staged'), ('submitted')) as bucket(bucket)
                left join bucket_counts using (bucket)
                cross join statistics
                order by bucket.bucket
                """,
                repeated_params,
            )
            rows = connection.fetch_all(
                common_sql
                + """
                    select batch_payload, task_payload, scope_month, invoice_count, total_amount
                    from scoped
                    where bucket = %s::text
                    order by created_at desc, business_batch_id desc
                    limit %s::integer offset %s::integer
                """,
                repeated_params + (bucket, page_size, (page - 1) * page_size),
            )
        counts = {"unsubmitted": 0, "staged": 0, "submitted": 0}
        statistics: dict[str, int] | None = None
        for row in count_rows:
            row_bucket = str(row.get("bucket") or "")
            if row_bucket in counts:
                counts[row_bucket] = int(row.get("count") or 0)
            if statistics is None:
                statistics = {
                    "invoice_count": int(row.get("etc_invoice_count") or 0),
                    "business_batch_count": int(row.get("business_batch_count") or 0),
                    "unsubmitted_batch_count": int(row.get("unsubmitted_batch_count") or 0),
                    "draft_batch_count": int(row.get("draft_batch_count") or 0),
                    "submitted_batch_count": int(row.get("submitted_batch_count") or 0),
                    "reconciliation_task_count": int(row.get("reconciliation_task_count") or 0),
                    "source_file_count": int(row.get("source_file_count") or 0),
                    "imported_invoice_count": int(row.get("imported_invoice_count") or 0),
                    "linked_canonical_invoice_count": int(row.get("linked_canonical_invoice_count") or 0),
                    "oa_draft_batch_count": int(row.get("oa_draft_batch_count") or 0),
                }
        return {
            "items": [
                {
                    "business_batch": row_payload(row, "batch_payload") or {},
                    "reconciliation_task": row_payload(row, "task_payload") or None,
                    "scope_month": row.get("scope_month"),
                    "invoice_count": int(row.get("invoice_count") or 0),
                    "total_amount": str(row.get("total_amount") or "0"),
                }
                for row in rows
            ],
            "counts": counts,
            "statistics": statistics,
            "total": counts[bucket],
        }

    def get_etc_business_batch_record(self, business_batch_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            select raw_payload
            from app.etc_business_batches
            where business_batch_id = %s
              and coalesce(legacy_mongo_id, '') !~ '^current_state:'
              and status not in ('deleted', 'superseded')
            """,
            (str(business_batch_id or "").strip(),),
        )
        payload = row_payload(row, "raw_payload")
        return dict(payload) if isinstance(payload, dict) else None

    def list_etc_invoice_records_by_ids(self, invoice_ids: list[str]) -> list[dict[str, Any]]:
        normalized_ids = [str(value).strip() for value in invoice_ids if str(value).strip()]
        if not normalized_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select etc_invoice_id, raw_payload
            from app.etc_invoices
            where etc_invoice_id = any(%s)
              and coalesce(legacy_mongo_id, '') !~ '^current_state:'
            """,
            (normalized_ids,),
        )
        by_id = {
            str(row.get("etc_invoice_id")): dict(payload)
            for row in rows
            if isinstance((payload := row_payload(row, "raw_payload")), dict)
        }
        return [by_id[invoice_id] for invoice_id in normalized_ids if invoice_id in by_id]

    def get_etc_reconciliation_task_record(self, task_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            "select raw_payload from app.etc_reconciliation_tasks where task_id = %s",
            (str(task_id or "").strip(),),
        )
        payload = row_payload(row, "raw_payload")
        return dict(payload) if isinstance(payload, dict) else None

    def save_etc_state(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            normalized = serialize_value(snapshot)
            invoices = normalized.get("invoices") if isinstance(normalized, dict) else None
            for invoice_id, payload in iter_mapping(invoices):
                connection.execute(
                    """
                    insert into app.etc_invoices(
                        legacy_mongo_id, etc_invoice_id, invoice_no, invoice_code, invoice_date,
                        scope_month, seller_name, buyer_name, amount, tax_amount, total_with_tax,
                        status, batch_id, task_id, business_batch_id, file_path, file_sha256, version, raw_payload
                    )
                    values (%s, %s, %s, %s, %s::date, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (etc_invoice_id) do update set
                        invoice_no = excluded.invoice_no,
                        invoice_code = excluded.invoice_code,
                        invoice_date = excluded.invoice_date,
                        scope_month = excluded.scope_month,
                        seller_name = excluded.seller_name,
                        buyer_name = excluded.buyer_name,
                        amount = excluded.amount,
                        tax_amount = excluded.tax_amount,
                        total_with_tax = excluded.total_with_tax,
                        status = excluded.status,
                        batch_id = excluded.batch_id,
                        task_id = excluded.task_id,
                        business_batch_id = excluded.business_batch_id,
                        file_path = excluded.file_path,
                        file_sha256 = excluded.file_sha256,
                        version = excluded.version,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        invoice_id,
                        invoice_id,
                        text(payload.get("invoice_number") or payload.get("invoice_no")),
                        text(payload.get("invoice_code")),
                        text(payload.get("issue_date") or payload.get("invoice_date")),
                        month_start(payload.get("issue_date") or payload.get("scope_month")),
                        text(payload.get("seller_name")),
                        text(payload.get("buyer_name")),
                        decimal_text(payload.get("amount_without_tax") or payload.get("amount")),
                        decimal_text(payload.get("tax_amount")),
                        decimal_text(payload.get("total_amount") or payload.get("total_with_tax")),
                        text(payload.get("status") or "unsubmitted"),
                        text(payload.get("current_batch_id") or payload.get("last_batch_id")),
                        text(payload.get("task_id") or payload.get("reconciliation_task_id")),
                        text(payload.get("business_batch_id")),
                        text(payload.get("xml_file_path") or payload.get("pdf_file_path")),
                        text(payload.get("xml_file_hash") or payload.get("pdf_file_hash")),
                        int_value(payload.get("version"), 1),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            import_batches = normalized.get("import_batches") if isinstance(normalized, dict) else None
            for batch_id, payload in iter_mapping(import_batches):
                connection.execute(
                    """
                    insert into app.etc_import_batches(legacy_mongo_id, batch_id, status, scope_month, invoice_count, raw_payload)
                    values (%s, %s, %s, %s::date, %s, %s)
                    on conflict (batch_id) do update set
                        status = excluded.status,
                        scope_month = excluded.scope_month,
                        invoice_count = excluded.invoice_count,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        batch_id,
                        batch_id,
                        text(payload.get("status") or "confirmed"),
                        month_start(payload.get("issue_date_start") or payload.get("created_at")),
                        int_value(payload.get("invoice_count"), 0),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            batches = normalized.get("batches") if isinstance(normalized, dict) else None
            submission_batch_payloads = {batch_id: payload for batch_id, payload in iter_mapping(batches)}
            for batch_id, payload in iter_mapping(batches):
                connection.execute(
                    """
                    insert into app.etc_submission_batches(
                        legacy_mongo_id, submission_batch_id, status, scope_month, invoice_ids,
                        submitted_by, submitted_at, version, raw_payload
                    )
                    values (%s, %s, %s, %s::date, %s, %s, %s::timestamptz, %s, %s)
                    on conflict (submission_batch_id) do update set
                        status = excluded.status,
                        scope_month = excluded.scope_month,
                        invoice_ids = excluded.invoice_ids,
                        submitted_by = excluded.submitted_by,
                        submitted_at = excluded.submitted_at,
                        version = excluded.version,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        batch_id,
                        batch_id,
                        text(payload.get("status") or "draft_creating"),
                        month_start(payload.get("issue_start_date") or payload.get("created_at")),
                        text_list(payload.get("invoice_ids")),
                        text(payload.get("submitted_by")),
                        text(payload.get("confirmed_at") or payload.get("submitted_at")),
                        int_value(payload.get("version"), 1),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            business_batches = normalized.get("business_batches") if isinstance(normalized, dict) else None
            for business_batch_id, payload in iter_mapping(business_batches):
                invoice_ids = text_list(payload.get("invoice_ids"))
                submission_batch_id = text(payload.get("submission_batch_id"))
                submission_payload = submission_batch_payloads.get(submission_batch_id or "") if submission_batch_id else None
                business_scope_month = self._etc_business_batch_scope_month(payload, submission_payload)
                business_invoice_count = self._etc_business_batch_invoice_count(payload, submission_payload, invoice_ids)
                business_total_amount = self._etc_business_batch_total_amount(payload, submission_payload)
                connection.execute(
                    """
                    insert into app.etc_business_batches(
                        legacy_mongo_id, business_batch_id, task_id, status, scope_month,
                        invoice_count, total_amount, import_attempts, audit_events, version, raw_payload
                    )
                    values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s)
                    on conflict (business_batch_id) do update set
                        task_id = excluded.task_id,
                        status = excluded.status,
                        scope_month = excluded.scope_month,
                        invoice_count = excluded.invoice_count,
                        total_amount = excluded.total_amount,
                        import_attempts = excluded.import_attempts,
                        audit_events = excluded.audit_events,
                        version = excluded.version,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        business_batch_id,
                        business_batch_id,
                        text(payload.get("task_id")),
                        text(payload.get("status") or "draft"),
                        month_start(business_scope_month),
                        business_invoice_count,
                        business_total_amount,
                        jsonb(payload.get("import_attempts") if isinstance(payload.get("import_attempts"), list) else []),
                        jsonb(payload.get("audit_events") if isinstance(payload.get("audit_events"), list) else []),
                        int_value(payload.get("version"), 1),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def save_etc_oa_draft_attempt(
        self,
        snapshot: dict[str, Any],
        *,
        business_batch_id: str,
        expected_version: int,
    ) -> bool:
        def write(connection: Any) -> bool:
            row = connection.fetch_one(
                "select version from app.etc_business_batches where business_batch_id = %s for update",
                (business_batch_id,),
            )
            if int_value(row.get("version") if isinstance(row, dict) else None, 0) != int(expected_version):
                return False
            PostgresOpsTaxEtcRepository(connection).save_etc_state(snapshot)
            return True

        return run_in_transaction(self._connection, write)

    @staticmethod
    def _etc_business_batch_scope_month(
        payload: dict[str, Any],
        submission_payload: dict[str, Any] | None,
    ) -> Any:
        submission_payload = submission_payload if isinstance(submission_payload, dict) else {}
        return (
            payload.get("scope_month")
            or submission_payload.get("scope_month")
            or submission_payload.get("issue_start_date")
            or submission_payload.get("passage_start_date")
            or payload.get("created_at")
            or submission_payload.get("created_at")
        )

    @staticmethod
    def _etc_business_batch_invoice_count(
        payload: dict[str, Any],
        submission_payload: dict[str, Any] | None,
        invoice_ids: list[str],
    ) -> int:
        submission_payload = submission_payload if isinstance(submission_payload, dict) else {}
        invoice_summary = payload.get("invoice_summary") if isinstance(payload.get("invoice_summary"), dict) else {}
        for candidate in (
            payload.get("etc_invoice_count"),
            invoice_summary.get("count"),
            submission_payload.get("etc_invoice_count"),
            submission_payload.get("invoice_count"),
        ):
            count = int_value(candidate, -1)
            if count >= 0:
                return count
        return len(invoice_ids)

    @staticmethod
    def _etc_business_batch_total_amount(
        payload: dict[str, Any],
        submission_payload: dict[str, Any] | None,
    ) -> str:
        submission_payload = submission_payload if isinstance(submission_payload, dict) else {}
        invoice_summary = payload.get("invoice_summary") if isinstance(payload.get("invoice_summary"), dict) else {}
        for candidate in (
            payload.get("oa_total_amount"),
            payload.get("total_amount"),
            invoice_summary.get("amount"),
            submission_payload.get("oa_total_amount"),
            submission_payload.get("total_amount"),
            submission_payload.get("etc_invoice_amount"),
        ):
            amount = PostgresOpsTaxEtcRepository._nonzero_decimal_text(candidate)
            if amount is not None:
                return amount
        return decimal_text(payload.get("total_with_tax")) or "0"

    @staticmethod
    def _nonzero_decimal_text(value: Any) -> str | None:
        normalized = decimal_text(value)
        if not normalized:
            return None
        try:
            if Decimal(normalized) == Decimal("0"):
                return None
        except (InvalidOperation, ValueError):
            return None
        return normalized

    def load_etc_reconciliation_state(self) -> dict[str, Any]:
        tasks = load_keyed_rows(
            self._connection,
            "select task_id as key, raw_payload from app.etc_reconciliation_tasks order by created_at, task_id",
        )
        tasks = {task_id: without_keys(payload, {"id"}) for task_id, payload in tasks.items()}
        if not tasks:
            return {}
        file_rows = self._connection.fetch_all(
            "select task_id, file_id as key, status, raw_payload "
            "from app.etc_reconciliation_files order by created_at, file_id"
        )
        files_by_task: dict[str, list[dict[str, Any]]] = {}
        formal_file_ids: dict[str, dict[str, Any]] = {}
        for row in file_rows:
            payload = row_payload(row, "raw_payload")
            if not isinstance(payload, dict):
                continue
            file_id = str(payload.get("file_id") or row.get("key") or "").strip()
            if file_id:
                formal_file_ids[file_id] = payload
            if str(row.get("status") or "").strip() == "deleted":
                continue
            task_id = str(payload.get("task_id") or row.get("task_id") or "").strip()
            if not task_id:
                continue
            files_by_task.setdefault(task_id, []).append(payload)
        for task_id, task_payload in tasks.items():
            task_status = str(task_payload.get("status") or "").strip() if isinstance(task_payload, dict) else ""
            if task_status == "deleted":
                continue
            if isinstance(task_payload, dict) and task_id in files_by_task and not task_payload.get("source_files"):
                task_payload["source_files"] = files_by_task[task_id]
        source_file_ids = {
            str(file.get("file_id")): file
            for task_payload in tasks.values()
            if isinstance(task_payload, dict)
            for file in task_payload.get("source_files", [])
            if isinstance(file, dict) and file.get("file_id")
        }
        return {
            "schema_version": 1,
            "task_counter": max_numeric_suffix(tasks),
            "file_counter": max_numeric_suffix(formal_file_ids or source_file_ids),
            "audit_counter": self._max_reconciliation_audit_counter(tasks),
            "tasks": tasks,
        }

    def save_etc_reconciliation_state(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            normalized = serialize_value(snapshot)
            tasks = normalized.get("tasks") if isinstance(normalized, dict) else None
            for task_id, payload in iter_mapping(tasks):
                source_files = payload.get("source_files") if isinstance(payload.get("source_files"), list) else []
                source_file = next((item for item in source_files if isinstance(item, dict)), {})
                task_status = text(payload.get("status") or "draft")
                connection.execute(
                    """
                    insert into app.etc_reconciliation_tasks(
                        legacy_mongo_id, task_id, status, scope_month, source_file_id,
                        result_summary, version, raw_payload
                    )
                    values (%s, %s, %s, %s::date, %s, %s, %s, %s)
                    on conflict (task_id) do update set
                        status = excluded.status,
                        scope_month = excluded.scope_month,
                        source_file_id = excluded.source_file_id,
                        result_summary = excluded.result_summary,
                        version = excluded.version,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        task_id,
                        task_id,
                        task_status,
                        month_start(payload.get("period_start") or payload.get("statement_period_start") or payload.get("created_at")),
                        text(source_file.get("file_id") if isinstance(source_file, dict) else None),
                        jsonb(self._reconciliation_result_summary(payload)),
                        int_value(payload.get("version"), 1),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
                if task_status == "deleted":
                    connection.execute("delete from app.etc_reconciliation_files where task_id = %s", (task_id,))
                    continue
                source_file_ids = [
                    file_id
                    for file_payload in source_files
                    if isinstance(file_payload, dict)
                    if (file_id := text(file_payload.get("file_id")))
                ]
                connection.execute(
                    """
                    update app.etc_reconciliation_files
                    set status = 'deleted', updated_at = now()
                    where task_id = %s
                      and status <> 'deleted'
                      and not (file_id = any(%s))
                    """,
                    (task_id, source_file_ids),
                )
                for file_payload in source_files:
                    if not isinstance(file_payload, dict):
                        continue
                    file_id = text(file_payload.get("file_id"))
                    if not file_id:
                        continue
                    connection.execute(
                        """
                        insert into app.etc_reconciliation_files(
                            legacy_mongo_id, task_id, file_id, file_kind, status,
                            file_path, file_sha256, raw_payload
                        )
                        values (%s, %s, %s, %s, 'stored', %s, %s, %s)
                        on conflict (file_id) do update set
                            task_id = excluded.task_id,
                            file_kind = excluded.file_kind,
                            status = excluded.status,
                            file_path = excluded.file_path,
                            file_sha256 = excluded.file_sha256,
                            raw_payload = excluded.raw_payload,
                            updated_at = now()
                        """,
                        (
                            file_id,
                            task_id,
                            file_id,
                            text(file_payload.get("source_kind") or "unknown"),
                            text(file_payload.get("stored_path") or file_payload.get("file_path")),
                            text(file_payload.get("sha256") or file_payload.get("file_sha256")),
                            jsonb({"normalized_payload": file_payload}),
                        ),
                    )

        run_in_transaction(self._connection, write)

    def save_historical_etc_repair_bundle_metadata(self, payload: dict[str, Any], *, file_object_id: str | None) -> None:
        normalized_bundle_id = text(payload.get("bundle_id") or payload.get("_id"))
        if not normalized_bundle_id:
            raise ValueError("bundle_id is required.")
        self._connection.execute(
            """
            insert into app.historical_etc_repair_bundles(
                legacy_mongo_id, bundle_id, file_object_id, status, metadata, raw_payload
            )
            values (%s, %s, %s::uuid, %s, %s, %s)
            on conflict (bundle_id) do update set
                file_object_id = excluded.file_object_id,
                status = excluded.status,
                metadata = excluded.metadata,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                normalized_bundle_id,
                normalized_bundle_id,
                file_object_id,
                text(payload.get("status") or "seeded"),
                jsonb({key: value for key, value in payload.items() if key not in {"_id", "bundle_id"}}),
                jsonb({"normalized_payload": payload}),
            ),
        )

    def load_historical_etc_repair_bundle_metadata(self) -> dict[str, dict[str, Any]]:
        rows = self._connection.fetch_all(
            "select bundle_id as key, raw_payload from app.historical_etc_repair_bundles order by bundle_id"
        )
        return {
            str(row.get("key")): payload
            for row in rows
            if isinstance((payload := row_payload(row, "raw_payload")), dict)
        }

    def save_historical_etc_repair_parsed_seed(self, *, bundle_id: str, parsed_seed: dict[str, Any]) -> dict[str, Any]:
        seed = {**serialize_value(parsed_seed), "bundle_id": bundle_id}
        seed_id = text(seed.get("seed_id") or seed.get("bundle_id") or bundle_id)
        if seed_id:
            self._connection.execute(
                """
                insert into app.historical_etc_repair_parsed_seeds(
                    legacy_mongo_id, seed_id, bundle_id, status, parsed_payload, raw_payload
                )
                values (%s, %s, %s, %s, %s, %s)
                on conflict (seed_id) do update set
                    bundle_id = excluded.bundle_id,
                    status = excluded.status,
                    parsed_payload = excluded.parsed_payload,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                """,
                (
                    seed_id,
                    seed_id,
                    text(seed.get("bundle_id") or bundle_id),
                    text(seed.get("status") or "parsed"),
                    jsonb(seed),
                    jsonb({"normalized_payload": seed}),
                ),
            )
        return seed

    def load_historical_etc_repair_parsed_seeds(self) -> dict[str, dict[str, Any]]:
        rows = self._connection.fetch_all(
            "select bundle_id as key, parsed_payload, raw_payload from app.historical_etc_repair_parsed_seeds order by bundle_id"
        )
        return {
            str(row.get("key")): without_keys(payload, {"_id"})
            for row in rows
            if isinstance((payload := row_payload(row, "parsed_payload", "raw_payload")), dict)
        }

    def load_historical_etc_repair_states(self) -> dict[str, dict[str, Any]]:
        rows = self._connection.fetch_all(
            "select state_id as key, state_payload, raw_payload from app.historical_etc_repair_states order by state_id"
        )
        return {
            str(row.get("key")): without_keys(payload, {"_id"})
            for row in rows
            if isinstance((payload := row_payload(row, "state_payload", "raw_payload")), dict)
        }

    def save_historical_etc_repair_states(self, states: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            normalized = serialize_value(states)
            for state_id, payload in iter_mapping(normalized):
                connection.execute(
                    """
                    insert into app.historical_etc_repair_states(
                        legacy_mongo_id, state_id, status, version, state_payload, raw_payload
                    )
                    values (%s, %s, %s, %s, %s, %s)
                    on conflict (state_id) do update set
                        status = excluded.status,
                        version = excluded.version,
                        state_payload = excluded.state_payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        state_id,
                        state_id,
                        text(payload.get("status") or "unknown"),
                        int_value(payload.get("version"), 1),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def load_background_jobs(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select job_id, raw_payload from job.background_jobs order by created_at, job_id")
        return {str(row.get("job_id")): row_payload(row, "raw_payload") for row in rows}

    def save_background_jobs(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            for job_id, payload in iter_mapping(snapshot):
                connection.execute(
                    """
                    insert into job.background_jobs(
                        job_id, job_type, status, owner_id, visibility, source,
                        affected_months, progress, result_summary, error, retry_mode,
                        attention, superseded_by_job_id, raw_payload
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (job_id) do update set
                        job_type = excluded.job_type,
                        status = excluded.status,
                        owner_id = excluded.owner_id,
                        visibility = excluded.visibility,
                        source = excluded.source,
                        affected_months = excluded.affected_months,
                        progress = excluded.progress,
                        result_summary = excluded.result_summary,
                        error = excluded.error,
                        retry_mode = excluded.retry_mode,
                        attention = excluded.attention,
                        superseded_by_job_id = excluded.superseded_by_job_id,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        job_id,
                        text(payload.get("job_type") or payload.get("type") or "unknown"),
                        text(payload.get("status") or "unknown"),
                        text(payload.get("owner_id")),
                        text(payload.get("visibility")),
                        text(payload.get("source")),
                        text_list(payload.get("affected_months") or payload.get("months")),
                        jsonb(payload.get("progress") if isinstance(payload.get("progress"), dict) else {}),
                        jsonb(payload.get("result_summary") if isinstance(payload.get("result_summary"), dict) else {}),
                        text(payload.get("error") or payload.get("last_error")),
                        text(payload.get("retry_mode")),
                        jsonb(payload.get("attention") if isinstance(payload.get("attention"), dict) else {}),
                        text(payload.get("superseded_by_job_id")),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def load_app_health_alerts(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select alert_id, raw_payload from audit.app_health_alerts order by alert_id")
        if not rows:
            return {}
        return normalize_app_health_alerts({str(row.get("alert_id")): row_payload(row, "raw_payload") for row in rows})

    def save_app_health_alerts(self, snapshot: dict[str, Any]) -> None:
        def write(connection: Any) -> None:
            records = snapshot.get("records") if isinstance(snapshot, dict) else None
            for alert_id, payload in iter_mapping(records if isinstance(records, dict) else snapshot):
                connection.execute(
                    """
                    insert into audit.app_health_alerts(alert_id, kind, scope, severity, status, payload, raw_payload)
                    values (%s, %s, %s, %s, %s, %s, %s)
                    on conflict (alert_id) do update set
                        kind = excluded.kind,
                        scope = excluded.scope,
                        severity = excluded.severity,
                        status = excluded.status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        alert_id,
                        text(payload.get("kind") or "unknown"),
                        text(payload.get("scope")),
                        text(payload.get("severity") or "info"),
                        text(payload.get("status") or "active"),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    @staticmethod
    def _max_reconciliation_audit_counter(tasks: dict[str, Any]) -> int:
        event_ids: dict[str, Any] = {}
        for payload in tasks.values():
            if not isinstance(payload, dict):
                continue
            audit_events = payload.get("audit_events") if isinstance(payload.get("audit_events"), list) else []
            for event in audit_events:
                if not isinstance(event, dict):
                    continue
                event_id = text(event.get("event_id"))
                if not event_id:
                    continue
                event_ids[event_id] = event
        return max_numeric_suffix(event_ids)

    @staticmethod
    def _reconciliation_result_summary(payload: dict[str, Any]) -> dict[str, Any]:
        summary_keys = (
            "approved_delta",
            "approved_delta_note",
            "oa_total_amount",
            "etc_invoice_amount",
            "supplement_amount",
            "etc_invoice_count",
            "supplement_count",
            "vehicle_plates",
            "confirmed_item_set_hash",
        )
        return {key: payload.get(key) for key in summary_keys if key in payload}
