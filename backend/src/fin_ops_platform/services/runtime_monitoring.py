from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.app_status_read_model_registry import (
    APP_STATUS_READ_MODEL_REGISTRY,
    read_model_by_scope_type,
)
from fin_ops_platform.services.rabbitmq_runtime import rabbitmq_event_routes
from fin_ops_platform.services.read_model_manifest import (
    READ_MODEL_MANIFEST,
    is_command_only_read_model_scope,
    read_model_manifest_by_refresh_event_type,
)
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, RuntimeQueueSettings
from fin_ops_platform.services.runtime_worker_registry import (
    read_model_event_types,
    registration_by_worker_kind,
    worker_registrations,
)


READ_MODEL_EVENT_TYPES: dict[str, tuple[str, str]] = read_model_event_types()
READ_MODEL_MANIFEST_BY_EVENT_TYPE = read_model_manifest_by_refresh_event_type()

EMPTY_PERCENTILES = {"p50": None, "p95": None, "p99": None}
READ_MODEL_REFRESH_METRIC_SAMPLE_LIMIT = 512
READ_MODEL_REFRESH_SLOW_EVENT_LIMIT = 20
READ_MODEL_REFRESH_CURRENT_WINDOWS = ("recent_15m", "recent_1h", "recent_6h")
RABBITMQ_PUBLISH_CONFIRM_METRIC_SAMPLE_LIMIT = 512

_CURRENT_EFFECTIVE_OUTBOX_EVENT_PREDICATE_SQL = """
not (
  event_type = 'cost_statistics.read_model.refresh'
  and coalesce(scope_type, raw_payload->>'scope_type', payload->>'scope_type', aggregate_type, '') = 'cost_statistics'
  and (
    coalesce(scope_key, raw_payload->>'scope_key', payload->>'scope_key', aggregate_id, '') = 'all'
    or coalesce(scope_key, raw_payload->>'scope_key', payload->>'scope_key', aggregate_id, '') ~ '^[0-9]{4}-[0-9]{2}$'
  )
)
"""
def _current_effective_outbox_event_predicate_sql(alias: str) -> str:
    prefix = f"{alias}."
    return f"""
not (
  {prefix}event_type = 'cost_statistics.read_model.refresh'
  and coalesce(
    {prefix}scope_type,
    {prefix}raw_payload->>'scope_type',
    {prefix}payload->>'scope_type',
    {prefix}aggregate_type,
    ''
  ) = 'cost_statistics'
  and (
    coalesce(
      {prefix}scope_key,
      {prefix}raw_payload->>'scope_key',
      {prefix}payload->>'scope_key',
      {prefix}aggregate_id,
      ''
    ) = 'all'
    or coalesce(
      {prefix}scope_key,
      {prefix}raw_payload->>'scope_key',
      {prefix}payload->>'scope_key',
      {prefix}aggregate_id,
      ''
    ) ~ '^[0-9]{{4}}-[0-9]{{2}}$'
  )
)
"""


def _active_dirty_scope_coverage_sql(alias: str) -> str:
    prefix = f"{alias}."
    scope_type_expr = (
        f"coalesce({prefix}scope_type, {prefix}raw_payload->>'scope_type', "
        f"{prefix}payload->>'scope_type', {prefix}aggregate_type, '')"
    )
    scope_key_expr = (
        f"coalesce({prefix}scope_key, {prefix}raw_payload->>'scope_key', "
        f"{prefix}payload->>'scope_key', {prefix}aggregate_id, '')"
    )
    return f"""
exists (
  select 1
  from job.read_model_dirty_scopes dirty
  where {prefix}event_type like '%%.read_model.refresh'
    and {prefix}status in ('failed', 'dead_lettered')
    and dirty.tenant_id = {prefix}tenant_id
    and coalesce(dirty.scope_type, '') = {scope_type_expr}
    and coalesce(dirty.scope_key, '') = {scope_key_expr}
    and dirty.status in ('pending', 'processing')
    and dirty.updated_at >= {prefix}updated_at
)
"""


def _command_only_parent_scope_sql(*, scope_type_sql: str, scope_key_sql: str) -> str:
    scope_types = ", ".join(
        "'" + entry.scope_type.replace("'", "''") + "'"
        for entry in READ_MODEL_MANIFEST.values()
        if entry.all_scope_semantics == "fan_out_command"
    )
    return f"({scope_type_sql} in ({scope_types}) and ({scope_key_sql} = 'all' or {scope_key_sql} like '%%:all'))"


def _command_only_parent_event_sql(*, event_type_sql: str, scope_key_sql: str) -> str:
    event_types = ", ".join(
        "'" + entry.refresh_event_type.replace("'", "''") + "'"
        for entry in READ_MODEL_MANIFEST.values()
        if entry.all_scope_semantics == "fan_out_command"
    )
    return f"({event_type_sql} in ({event_types}) and ({scope_key_sql} = 'all' or {scope_key_sql} like '%%:all'))"


def _current_effective_outbox_attention_predicate_sql(alias: str) -> str:
    prefix = f"{alias}."
    scope_type_expr = (
        f"coalesce({prefix}scope_type, {prefix}raw_payload->>'scope_type', "
        f"{prefix}payload->>'scope_type', {prefix}aggregate_type, '')"
    )
    scope_key_expr = (
        f"coalesce({prefix}scope_key, {prefix}raw_payload->>'scope_key', "
        f"{prefix}payload->>'scope_key', {prefix}aggregate_id, '')"
    )
    command_only_parent = _command_only_parent_event_sql(
        event_type_sql=f"{prefix}event_type",
        scope_key_sql=scope_key_expr,
    )
    return f"""
{_current_effective_outbox_event_predicate_sql(alias)}
and not (
  exists (
    select 1
    from job.outbox_events newer
    where newer.tenant_id = {prefix}tenant_id
      and newer.event_type = {prefix}event_type
      and coalesce(newer.scope_type, newer.raw_payload->>'scope_type', newer.payload->>'scope_type', newer.aggregate_type, '') =
          {scope_type_expr}
      and coalesce(newer.scope_key, newer.raw_payload->>'scope_key', newer.payload->>'scope_key', newer.aggregate_id, '') =
          {scope_key_expr}
      and newer.status in ('pending', 'processing', 'done')
      and newer.id <> {prefix}id
      and (
        newer.created_at > {prefix}created_at
        or (newer.created_at = {prefix}created_at and newer.id > {prefix}id)
      )
  )
  or
  exists (
    select 1
    from job.outbox_events done
    where done.tenant_id = {prefix}tenant_id
      and done.event_type = {prefix}event_type
      and coalesce(done.scope_type, done.raw_payload->>'scope_type', done.payload->>'scope_type', done.aggregate_type, '') =
          {scope_type_expr}
      and coalesce(done.scope_key, done.raw_payload->>'scope_key', done.payload->>'scope_key', done.aggregate_id, '') =
          {scope_key_expr}
      and done.status = 'done'
      and done.updated_at > {prefix}updated_at
  )
  or (
    not {command_only_parent}
    and exists (
      select 1
      from read_model.app_status_readiness readiness
      where readiness.tenant_id = {prefix}tenant_id
        and coalesce(readiness.scope_type, '') = {scope_type_expr}
        and coalesce(readiness.scope_key, '') = {scope_key_expr}
        and readiness.status = 'fresh'
        and readiness.updated_at > {prefix}updated_at
    )
  )
  or {_active_dirty_scope_coverage_sql(alias)}
)
"""


def _current_effective_dirty_scope_predicate_sql(alias: str | None = None) -> str:
    prefix = f"{alias}." if alias else ""
    scope_type_expr = f"coalesce({prefix}scope_type, '')"
    scope_key_expr = f"coalesce({prefix}scope_key, '')"
    command_only_parent = _command_only_parent_scope_sql(
        scope_type_sql=scope_type_expr,
        scope_key_sql=scope_key_expr,
    )
    return f"""
not (
  {prefix}scope_type = 'cost_statistics'
  and ({prefix}scope_key = 'all' or {prefix}scope_key ~ '^[0-9]{{4}}-[0-9]{{2}}$')
)
and not (
  not {command_only_parent}
  and exists (
    select 1
    from read_model.app_status_readiness readiness
    where readiness.tenant_id = {prefix}tenant_id
      and coalesce(readiness.scope_type, '') = {scope_type_expr}
      and coalesce(readiness.scope_key, '') = {scope_key_expr}
      and readiness.status = 'fresh'
      and readiness.updated_at > {prefix}updated_at
  )
)
"""


class RuntimeMonitoringRepository:
    def __init__(self, connection: Any, rabbitmq_metrics_provider: Any | None = None) -> None:
        self._connection = connection
        self._rabbitmq_metrics_provider = rabbitmq_metrics_provider

    def app_status_runtime_snapshot(self) -> dict[str, dict[str, dict[str, Any]]]:
        try:
            return {
                "read_model_statuses": self._app_status_read_model_statuses(),
                "outbox_statuses": self._app_status_outbox_statuses(),
                "worker_statuses": self._app_status_worker_statuses(),
            }
        except Exception as exc:
            payload = {
                "status": "unavailable",
                "last_error": str(exc) or exc.__class__.__name__,
            }
            return {
                "read_model_statuses": {"__runtime__": dict(payload)},
                "outbox_statuses": {"__runtime__": dict(payload)},
                "worker_statuses": {"__runtime__": dict(payload)},
            }

    def operation_barrier_runtime_snapshot(
        self,
        targets: list[dict[str, str]],
    ) -> dict[str, dict[str, dict[str, Any]]]:
        """Return the existing runtime facts for only the requested barrier scopes."""
        normalized_targets = _normalized_operation_barrier_targets(targets)
        if not normalized_targets:
            return {
                "read_model_statuses": {},
                "outbox_statuses": {},
                "worker_statuses": {},
            }
        try:
            return {
                "read_model_statuses": self._app_status_read_model_statuses(normalized_targets),
                "outbox_statuses": self._app_status_outbox_statuses(normalized_targets),
                "worker_statuses": self._app_status_worker_statuses(
                    {
                        target["worker_instance"]
                        for target in normalized_targets
                        if target["worker_instance"]
                    }
                ),
            }
        except Exception as exc:
            payload = {
                "status": "unavailable",
                "last_error": str(exc) or exc.__class__.__name__,
            }
            return {
                "read_model_statuses": {"__runtime__": dict(payload)},
                "outbox_statuses": {"__runtime__": dict(payload)},
                "worker_statuses": {"__runtime__": dict(payload)},
            }

    def record_read_model_readiness(
        self,
        *,
        read_model_key: str,
        scope_type: str,
        scope_key: str,
        status: str,
        tenant_id: str = "default",
        schema_version: str = "",
        source_versions: dict[str, Any] | None = None,
        row_count: int | None = None,
        generated_at: object | None = None,
        last_error: str | None = None,
        raw_payload: dict[str, Any] | None = None,
    ) -> None:
        normalized_status = str(status or "").strip().lower()
        if normalized_status not in {
            "fresh",
            "missing",
            "refreshing",
            "stale",
            "schema_mismatch",
            "source_mismatch",
            "failed",
            "unavailable",
        }:
            raise ValueError(f"Unsupported read model readiness status: {status!r}.")
        self._connection.execute(
            """
            insert into read_model.app_status_readiness (
                tenant_id,
                read_model_key,
                scope_type,
                scope_key,
                status,
                schema_version,
                source_versions,
                row_count,
                generated_at,
                last_error,
                raw_payload,
                updated_at
            ) values (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s::jsonb,
                %s,
                %s,
                %s,
                %s::jsonb,
                now()
            )
            on conflict (tenant_id, read_model_key, scope_type, scope_key)
            do update set
                status = excluded.status,
                schema_version = excluded.schema_version,
                source_versions = excluded.source_versions,
                row_count = excluded.row_count,
                generated_at = excluded.generated_at,
                last_error = excluded.last_error,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                str(tenant_id or "default"),
                str(read_model_key or "").strip(),
                str(scope_type or "").strip(),
                str(scope_key or "").strip(),
                normalized_status,
                str(schema_version or ""),
                _json_payload(source_versions or {}),
                row_count,
                generated_at,
                last_error,
                _json_payload(raw_payload or {}),
            ),
        )

    def app_status_readiness_backfill_fact(self, read_model_key: str, *, tenant_id: str = "default") -> dict[str, Any] | None:
        return _app_status_readiness_backfill_fact(self._connection, read_model_key, tenant_id=tenant_id)

    def _app_status_read_model_statuses(
        self,
        targets: list[dict[str, str]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = self._app_status_readiness_statuses(targets)
        definitions_by_scope = read_model_by_scope_type()
        target_filter_sql, target_filter_params = _operation_barrier_scope_filter_sql(
            targets,
            read_model_key_sql=None,
            scope_type_sql="dirty.scope_type",
            scope_key_sql="dirty.scope_key",
        )
        rows = self._connection.fetch_all(
            f"""
            select
                dirty.scope_type,
                dirty.scope_key,
                dirty.status,
                count(*)::bigint as count,
                max(dirty.last_error) as last_error,
                max(dirty.updated_at)::text as updated_at,
                bool_or(
                    exists (
                        select 1
                        from read_model.app_status_readiness readiness
                        where readiness.tenant_id = dirty.tenant_id
                          and coalesce(readiness.scope_type, '') = coalesce(dirty.scope_type, '')
                          and coalesce(readiness.scope_key, '') = coalesce(dirty.scope_key, '')
                          and readiness.status = 'fresh'
                          and readiness.updated_at > dirty.updated_at
                    )
                ) as covered_by_later_readiness
            from job.read_model_dirty_scopes dirty
            where dirty.tenant_id = 'default'
              and dirty.status in ('pending', 'processing', 'failed')
              {target_filter_sql}
            group by dirty.scope_type, dirty.scope_key, dirty.status
            """,
            target_filter_params,
        )
        for row in rows:
            scope_type = str(row.get("scope_type") or "").strip()
            if not scope_type:
                continue
            read_model_key = definitions_by_scope.get(scope_type).key if scope_type in definitions_by_scope else scope_type
            scope_key = str(row.get("scope_key") or "").strip()
            if _truthy(row.get("covered_by_later_readiness")) and not is_command_only_read_model_scope(
                read_model_key,
                scope_key,
            ):
                continue
            last_error = str(row.get("last_error") or "").strip()
            updated_at = str(row.get("updated_at") or "").strip()
            scope_status = _app_status_dirty_scope_status(row.get("status"))
            if _is_legacy_cost_statistics_scope(scope_type, row.get("scope_key")):
                current = grouped.setdefault(
                    read_model_key,
                    {
                        "status": "missing",
                        "reason": "readiness record missing",
                        "count": 0,
                        "details": [],
                        "scopes": [],
                    },
                )
                historical_scopes = current.setdefault("historical_scopes", [])
                if isinstance(historical_scopes, list):
                    historical_scopes.append(
                        _app_status_historical_read_model_scope_payload(
                            read_model_key=read_model_key,
                            scope_type=scope_type,
                            scope_key=row.get("scope_key"),
                            status=scope_status,
                            last_error=last_error,
                            updated_at=updated_at,
                            history_reason="legacy_scope_contract",
                        )
                    )
                continue
            current = grouped.setdefault(read_model_key, {"status": "missing", "count": 0, "details": [], "scopes": []})
            current["count"] = int(current.get("count") or 0) + (_optional_int(row.get("count")) or 0)
            if updated_at:
                current["updated_at"] = updated_at
            scopes = current.setdefault("scopes", [])
            if isinstance(scopes, list):
                _upsert_app_status_read_model_scope(
                    scopes,
                    _app_status_read_model_scope_payload(
                        read_model_key=read_model_key,
                        scope_type=scope_type,
                        scope_key=row.get("scope_key"),
                        status=scope_status,
                        last_error=last_error,
                        updated_at=updated_at,
                    ),
                )
                current["status"] = _app_status_status_from_scopes(scopes, fallback=str(current.get("status") or "missing"))
                current_error = _app_status_last_error_from_scopes(scopes)
                if current_error:
                    current["last_error"] = current_error
                elif str(current.get("status") or "").strip().lower() not in {"failed", "unavailable"}:
                    current.pop("last_error", None)
        target_keys = (
            {target["read_model_key"] for target in targets}
            if targets is not None
            else set(APP_STATUS_READ_MODEL_REGISTRY)
        )
        for key in target_keys:
            definition = APP_STATUS_READ_MODEL_REGISTRY.get(key)
            if definition is None:
                continue
            grouped.setdefault(
                key,
                {
                    "status": "missing",
                    "reason": "readiness record missing",
                    "scope_type": definition.scope_type,
                    "count": 0,
                    "scopes": [],
                },
            )
        return grouped

    def _app_status_readiness_statuses(
        self,
        targets: list[dict[str, str]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        target_filter_sql, target_filter_params = _operation_barrier_scope_filter_sql(
            targets,
            read_model_key_sql="read_model_key",
            scope_type_sql="scope_type",
            scope_key_sql="scope_key",
        )
        rows = self._connection.fetch_all(
            f"""
            select
                read_model_key,
                scope_type,
                scope_key,
                status,
                schema_version,
                source_versions,
                row_count,
                generated_at::text as generated_at,
                updated_at::text as updated_at,
                last_error
            from read_model.app_status_readiness
            where tenant_id = 'default'
              {target_filter_sql}
            """,
            target_filter_params,
        )
        grouped: dict[str, dict[str, Any]] = {}
        historical_scopes_by_key: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            key = str(row.get("read_model_key") or "").strip()
            if not key:
                continue
            status = str(row.get("status") or "missing").strip().lower() or "missing"
            if is_command_only_read_model_scope(key, str(row.get("scope_key") or "")):
                historical_scopes_by_key.setdefault(key, []).append(
                    _app_status_historical_read_model_scope_payload(
                        read_model_key=key,
                        scope_type=row.get("scope_type"),
                        scope_key=row.get("scope_key"),
                        status=status,
                        last_error=row.get("last_error"),
                        updated_at=row.get("updated_at"),
                        history_reason="fan_out_command_scope",
                    )
                )
                continue
            if _is_legacy_cost_statistics_scope(row.get("scope_type"), row.get("scope_key")):
                historical_scopes_by_key.setdefault(key, []).append(
                    _app_status_historical_read_model_scope_payload(
                        read_model_key=key,
                        scope_type=row.get("scope_type"),
                        scope_key=row.get("scope_key"),
                        status=status,
                        last_error=row.get("last_error"),
                        updated_at=row.get("updated_at"),
                        history_reason="legacy_scope_contract",
                    )
                )
                continue
            current = grouped.setdefault(
                key,
                {
                    "status": "fresh",
                    "count": 0,
                    "scope_type": row.get("scope_type"),
                    "scope_key": row.get("scope_key"),
                    "schema_version": row.get("schema_version"),
                    "source_versions": row.get("source_versions"),
                    "row_count": row.get("row_count"),
                    "generated_at": row.get("generated_at"),
                    "updated_at": row.get("updated_at"),
                    "last_error": row.get("last_error"),
                    "scopes": [],
                },
            )
            scopes = current.setdefault("scopes", [])
            if isinstance(scopes, list):
                scopes.append(
                    _app_status_read_model_scope_payload(
                        read_model_key=key,
                        scope_type=row.get("scope_type"),
                        scope_key=row.get("scope_key"),
                        status=status,
                        last_error=row.get("last_error"),
                        updated_at=row.get("updated_at"),
                    )
                )
            current["status"] = _max_app_status(str(current.get("status") or "fresh"), status)
            current["count"] = int(current.get("count") or 0) + 1
            if row.get("last_error"):
                current["last_error"] = row.get("last_error")
            if row.get("updated_at"):
                current["updated_at"] = row.get("updated_at")
            if row.get("generated_at"):
                current["generated_at"] = row.get("generated_at")
        for key, historical_scopes in historical_scopes_by_key.items():
            current = grouped.setdefault(
                key,
                {
                    "status": "missing",
                    "reason": "readiness record missing",
                    "count": 0,
                    "scopes": [],
                },
            )
            target_scopes = current.setdefault("historical_scopes", [])
            if isinstance(target_scopes, list):
                target_scopes.extend(historical_scopes)
        return grouped

    def _app_status_outbox_statuses(
        self,
        targets: list[dict[str, str]] | None = None,
    ) -> dict[str, dict[str, Any]]:
        if targets is not None:
            rows = self._operation_barrier_outbox_status_rows(targets)
            return self._group_app_status_outbox_rows(rows)
        target_filter_sql, target_filter_params = _operation_barrier_scope_filter_sql(
            targets,
            read_model_key_sql=None,
            event_type_sql="e.event_type",
            scope_type_sql=(
                "coalesce(e.scope_type, e.raw_payload->>'scope_type', "
                "e.payload->>'scope_type', e.aggregate_type, '')"
            ),
            scope_key_sql=(
                "coalesce(e.scope_key, e.raw_payload->>'scope_key', "
                "e.payload->>'scope_key', e.aggregate_id, '')"
            ),
        )
        rows = self._connection.fetch_all(
            f"""
            select
                e.event_type,
                coalesce(e.scope_type, e.raw_payload->>'scope_type', e.payload->>'scope_type', e.aggregate_type, '') as scope_type,
                coalesce(e.scope_key, e.raw_payload->>'scope_key', e.payload->>'scope_key', e.aggregate_id, '') as scope_key,
                case
                  when e.status in ('failed', 'dead_lettered') then e.status
                  when e.publish_status = 'failed' then 'publish_failed'
                  when e.publish_status = 'publishing' then 'publishing'
                  else e.status
                end as status,
                count(*)::bigint as count,
                max(e.last_error) as last_error,
                max(e.updated_at)::text as updated_at,
                bool_or(
                    exists (
                        select 1
                        from job.outbox_events newer
                        where newer.tenant_id = e.tenant_id
                          and newer.event_type = e.event_type
                          and coalesce(newer.scope_type, newer.raw_payload->>'scope_type', newer.payload->>'scope_type', newer.aggregate_type, '') =
                              coalesce(e.scope_type, e.raw_payload->>'scope_type', e.payload->>'scope_type', e.aggregate_type, '')
                          and coalesce(newer.scope_key, newer.raw_payload->>'scope_key', newer.payload->>'scope_key', newer.aggregate_id, '') =
                              coalesce(e.scope_key, e.raw_payload->>'scope_key', e.payload->>'scope_key', e.aggregate_id, '')
                          and newer.status in ('pending', 'processing', 'done')
                          and newer.id <> e.id
                          and (
                            newer.created_at > e.created_at
                            or (newer.created_at = e.created_at and newer.id > e.id)
                          )
                    )
                ) as covered_by_later_event,
                bool_or(
                    exists (
                        select 1
                        from job.outbox_events done
                        where done.tenant_id = e.tenant_id
                          and done.event_type = e.event_type
                          and coalesce(done.scope_type, done.raw_payload->>'scope_type', done.payload->>'scope_type', done.aggregate_type, '') =
                              coalesce(e.scope_type, e.raw_payload->>'scope_type', e.payload->>'scope_type', e.aggregate_type, '')
                          and coalesce(done.scope_key, done.raw_payload->>'scope_key', done.payload->>'scope_key', done.aggregate_id, '') =
                              coalesce(e.scope_key, e.raw_payload->>'scope_key', e.payload->>'scope_key', e.aggregate_id, '')
                          and done.status = 'done'
                          and done.updated_at > e.updated_at
                    )
                ) as covered_by_later_done,
                bool_or(
                    exists (
                        select 1
                        from read_model.app_status_readiness readiness
                        where readiness.tenant_id = e.tenant_id
                          and coalesce(readiness.scope_type, '') =
                              coalesce(e.scope_type, e.raw_payload->>'scope_type', e.payload->>'scope_type', e.aggregate_type, '')
                          and coalesce(readiness.scope_key, '') =
                              coalesce(e.scope_key, e.raw_payload->>'scope_key', e.payload->>'scope_key', e.aggregate_id, '')
                          and readiness.status = 'fresh'
                          and readiness.updated_at > e.updated_at
                    )
                ) as covered_by_later_readiness,
                bool_or(
                    {_active_dirty_scope_coverage_sql("e")}
                ) as covered_by_active_dirty_scope
            from job.outbox_events e
            where (
                e.status in ('pending', 'processing', 'publishing', 'publish_failed', 'failed', 'dead_lettered')
                or (
                    e.status <> 'done'
                    and e.publish_status in ('publishing', 'failed')
                )
            )
              {target_filter_sql}
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.event_type, 2, 3, 4
            """,
            target_filter_params,
        )
        return self._group_app_status_outbox_rows(rows)

    def _operation_barrier_outbox_status_rows(
        self,
        targets: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Load only the latest current-effective outbox fact per barrier scope."""
        target_event_types = [target["refresh_event_type"] for target in targets]
        target_scope_types = [target["scope_type"] for target in targets]
        target_scope_keys = [target["scope_key"] for target in targets]
        command_only_parent = _command_only_parent_event_sql(
            event_type_sql="e.event_type",
            scope_key_sql="e.scope_key",
        )
        return self._connection.fetch_all(
            f"""
            with barrier_target(target_event_type, target_scope_type, target_scope_key) as (
              select *
              from unnest(%s::text[], %s::text[], %s::text[])
            ),
            candidate_scope(target_event_type, target_scope_type, candidate_scope_key) as (
              select target_event_type, target_scope_type, target_scope_key
              from barrier_target
              union
              select target_event_type, target_scope_type, 'all'
              from barrier_target
              where target_scope_key <> 'all'
            ),
            latest_events as (
              select latest.*
              from candidate_scope target
              cross join lateral (
                select
                  event.id,
                  event.tenant_id,
                  event.event_type,
                  coalesce(
                    event.scope_type,
                    event.raw_payload->>'scope_type',
                    event.payload->>'scope_type',
                    event.aggregate_type,
                    ''
                  ) as scope_type,
                  coalesce(
                    event.scope_key,
                    event.raw_payload->>'scope_key',
                    event.payload->>'scope_key',
                    event.aggregate_id,
                    ''
                  ) as scope_key,
                  event.status,
                  event.publish_status,
                  event.last_error,
                  event.publish_last_error,
                  event.updated_at
                from job.outbox_events event
                where event.tenant_id = 'default'
                  and event.event_type = target.target_event_type
                  and coalesce(
                        event.scope_type,
                        event.raw_payload->>'scope_type',
                        event.payload->>'scope_type',
                        event.aggregate_type,
                        ''
                      ) = target.target_scope_type
                  and coalesce(
                        event.scope_key,
                        event.raw_payload->>'scope_key',
                        event.payload->>'scope_key',
                        event.aggregate_id,
                        ''
                      ) = target.candidate_scope_key
                  and event.status in (
                    'pending',
                    'processing',
                    'publishing',
                    'publish_failed',
                    'failed',
                    'dead_lettered',
                    'done'
                  )
                order by event.created_at desc, event.id desc
                limit 1
              ) latest
            )
            select
              e.event_type,
              e.scope_type,
              e.scope_key,
              case
                when e.status in ('failed', 'dead_lettered') then e.status
                when e.publish_status = 'failed' then 'publish_failed'
                when e.publish_status = 'publishing' then 'publishing'
                else e.status
              end as status,
              1::bigint as count,
              coalesce(nullif(e.last_error, ''), e.publish_last_error) as last_error,
              e.updated_at::text as updated_at,
              false as covered_by_later_event,
              false as covered_by_later_done,
              false as covered_by_later_readiness,
              false as covered_by_active_dirty_scope
            from latest_events e
            where (
                e.status in ('pending', 'processing', 'publishing', 'publish_failed', 'failed', 'dead_lettered')
                or (e.status <> 'done' and e.publish_status in ('publishing', 'failed'))
              )
              and (
                {command_only_parent}
                or not exists (
                  select 1
                  from read_model.app_status_readiness readiness
                  where readiness.tenant_id = e.tenant_id
                    and coalesce(readiness.scope_type, '') = e.scope_type
                    and coalesce(readiness.scope_key, '') = e.scope_key
                    and readiness.status = 'fresh'
                    and readiness.updated_at > e.updated_at
                )
              )
              and not (
                e.status in ('failed', 'dead_lettered')
                and exists (
                  select 1
                  from job.read_model_dirty_scopes dirty
                  where dirty.tenant_id = e.tenant_id
                    and coalesce(dirty.scope_type, '') = e.scope_type
                    and coalesce(dirty.scope_key, '') = e.scope_key
                    and dirty.status in ('pending', 'processing')
                    and dirty.updated_at >= e.updated_at
                )
              )
            """,
            (target_event_types, target_scope_types, target_scope_keys),
        )

    @staticmethod
    def _group_app_status_outbox_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        scope_indexes: dict[str, dict[tuple[str, str], dict[str, Any]]] = {}
        for row in rows:
            event_type = str(row.get("event_type") or "").strip()
            if not event_type:
                continue
            if _is_historical_outbox_status(row):
                continue
            row_count = _optional_int(row.get("count")) or 0
            row_status = str(row.get("status") or "")
            updated_at = str(row.get("updated_at") or "").strip()
            last_error = str(row.get("last_error") or "").strip()
            current = grouped.setdefault(event_type, {"status": "ready", "count": 0})
            current["count"] = int(current.get("count") or 0) + row_count
            current["status"] = _max_app_outbox_status(
                str(current.get("status") or "ready"),
                row_status,
            )
            if last_error:
                current["last_error"] = last_error
            if updated_at:
                current["updated_at"] = updated_at
            scope_type = str(row.get("scope_type") or "").strip()
            scope_key = str(row.get("scope_key") or "").strip()
            if scope_type or scope_key:
                scope_index = scope_indexes.setdefault(event_type, {})
                scope_payload = scope_index.setdefault(
                    (scope_type, scope_key),
                    {
                        "event_type": event_type,
                        "scope_type": scope_type,
                        "scope_key": scope_key,
                        "status": "ready",
                        "count": 0,
                    },
                )
                scope_payload["count"] = int(scope_payload.get("count") or 0) + row_count
                scope_payload["status"] = _max_app_outbox_status(
                    str(scope_payload.get("status") or "ready"),
                    row_status,
                )
                if last_error:
                    scope_payload["last_error"] = last_error
                if updated_at:
                    scope_payload["updated_at"] = updated_at
        for event_type, scope_index in scope_indexes.items():
            if event_type in grouped:
                grouped[event_type]["scopes"] = list(scope_index.values())
        return grouped

    def _app_status_worker_statuses(
        self,
        worker_instances: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        statuses: dict[str, dict[str, Any]] = {}
        for row in self.dashboard_worker_metrics(worker_instances=worker_instances):
            if row.get("required") is False and row.get("current_effective") is False:
                continue
            instance = str(row.get("worker_instance") or "").strip()
            if not instance or (worker_instances is not None and instance not in worker_instances):
                continue
            statuses[instance] = {
                "status": _app_status_worker_status(row.get("status")),
                "worker_id": row.get("worker_id"),
                "worker_kind": row.get("worker_kind"),
                "heartbeat_lag_seconds": row.get("heartbeat_lag_seconds"),
                "warning_code": row.get("warning_code"),
                "required": row.get("required"),
            }
        return statuses

    def health_summary(self, *, stale_after_seconds: int = 300) -> dict[str, Any]:
        queue_rows = self._connection.fetch_all(
            f"""
            select e.status, count(*)::bigint as count
            from job.outbox_events e
            where e.status <> 'done'
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.status
            order by e.status
            """
        )
        age_row = self._connection.fetch_one(
            f"""
            select extract(epoch from max(now() - e.created_at))::float as max_pending_age_seconds
            from job.outbox_events e
            where e.status = 'pending'
              and {_current_effective_outbox_attention_predicate_sql("e")}
            """
        )
        dirty_count_rows = self._connection.fetch_all(
            f"""
            select status, count(*)::bigint as count
            from job.read_model_dirty_scopes
            where {_current_effective_dirty_scope_predicate_sql()}
            group by status
            order by status
            """
        )
        stale_rows = self._connection.fetch_all(
            f"""
            select
              tenant_id,
              scope_type,
              scope_key,
              status,
              extract(epoch from now() - updated_at)::float as age_seconds,
              attempts,
              last_error
            from job.read_model_dirty_scopes
            where status in ('pending', 'processing', 'failed')
              and updated_at < now() - (%s * interval '1 second')
            order by updated_at, tenant_id, scope_type, scope_key
            limit 20
            """,
            (stale_after_seconds,),
        )
        worker_lag_row = self._connection.fetch_one(
            """
            with latest_worker_kind_heartbeats as (
              select distinct on (worker_kind)
                worker_kind,
                last_seen_at
              from job.runtime_worker_heartbeats
              order by worker_kind, last_seen_at desc
            )
            select extract(epoch from max(now() - last_seen_at))::float as max_worker_heartbeat_lag_seconds
            from latest_worker_kind_heartbeats
            where worker_kind <> 'runtime'
            """
        )
        refresh_metric_rows = self._connection.fetch_all(
            """
            with event_type_filter(event_type) as (
              select unnest(%s::text[])
            ),
            recent_refresh_events as (
              select
                refresh_event.event_type,
                refresh_event.status,
                refresh_event.created_at,
                refresh_event.processed_at,
                refresh_event.updated_at,
                case
                  when refresh_event.status = 'done'
                   and refresh_event.raw_payload->'runtime_result' ? 'duration_ms'
                    then ((refresh_event.raw_payload->'runtime_result'->>'duration_ms')::numeric)
                  else null
                end as duration_ms,
                case
                  when refresh_event.status = 'done'
                   and refresh_event.processed_at is not null
                    then greatest(extract(epoch from (refresh_event.processed_at - refresh_event.created_at)) * 1000, 0)
                  else null
                end as enqueue_to_fresh_ms
              from event_type_filter
              cross join lateral (
                select
                  event_type,
                  status,
                  created_at,
                  processed_at,
                  updated_at,
                  raw_payload
                from job.outbox_events
                where event_type = event_type_filter.event_type
                  and event_type like '%%.read_model.refresh'
                  and (
                    status in ('failed', 'dead_lettered')
                    or (
                      status = 'done'
                      and raw_payload->'runtime_result' ? 'duration_ms'
                    )
                  )
                order by updated_at desc
                limit %s
              ) refresh_event
            ),
            metric_windows(window_name, started_at) as (
              values
                ('all_time', '-infinity'::timestamptz),
                ('recent_15m', now() - interval '15 minutes'),
                ('recent_1h', now() - interval '1 hour'),
                ('recent_6h', now() - interval '6 hours')
            )
            select
              metric_windows.window_name,
              case
                when grouping(recent_refresh_events.event_type) = 1 then '__all__'
                else recent_refresh_events.event_type
              end as event_type,
              (percentile_cont(0.5) within group (
                order by duration_ms
              ) filter (where duration_ms is not null))::float as p50_ms,
              (percentile_cont(0.95) within group (
                order by duration_ms
              ) filter (where duration_ms is not null))::float as p95_ms,
              (percentile_cont(0.99) within group (
                order by duration_ms
              ) filter (where duration_ms is not null))::float as p99_ms,
              (percentile_cont(0.5) within group (
                order by enqueue_to_fresh_ms
              ) filter (where enqueue_to_fresh_ms is not null))::float as enqueue_p50_ms,
              (percentile_cont(0.95) within group (
                order by enqueue_to_fresh_ms
              ) filter (where enqueue_to_fresh_ms is not null))::float as enqueue_p95_ms,
              (percentile_cont(0.99) within group (
                order by enqueue_to_fresh_ms
              ) filter (where enqueue_to_fresh_ms is not null))::float as enqueue_p99_ms,
              count(*) filter (where duration_ms is not null)::bigint as completed_sample_count,
              count(*) filter (where status in ('failed', 'dead_lettered'))::bigint as failed_count,
              count(*)::bigint as read_model_refresh_total,
              (max(updated_at) filter (where duration_ms is not null))::text as last_completed_at,
              (max(processed_at) filter (where enqueue_to_fresh_ms is not null))::text as last_fresh_at
            from recent_refresh_events
            join metric_windows
              on recent_refresh_events.created_at >= metric_windows.started_at
            group by grouping sets ((metric_windows.window_name, recent_refresh_events.event_type), (metric_windows.window_name))
            """,
            (list(READ_MODEL_EVENT_TYPES.keys()), READ_MODEL_REFRESH_METRIC_SAMPLE_LIMIT),
        )
        slow_event_rows = self._connection.fetch_all(
            """
            with event_type_filter(event_type) as (
              select unnest(%s::text[])
            ),
            slow_refresh_event_samples as (
              select
                refresh_event.id::text as event_id,
                refresh_event.event_type,
                coalesce(
                  refresh_event.scope_type,
                  refresh_event.payload->>'scope_type',
                  refresh_event.aggregate_type,
                  ''
                ) as scope_type,
                coalesce(
                  refresh_event.scope_key,
                  refresh_event.payload->>'scope_key',
                  refresh_event.aggregate_id,
                  ''
                ) as scope_key,
                refresh_event.status,
                refresh_event.source_version,
                refresh_event.priority,
                refresh_event.created_at::text as created_at,
                refresh_event.processed_at::text as processed_at,
                refresh_event.updated_at::text as updated_at,
                case
                  when refresh_event.status = 'done'
                   and refresh_event.raw_payload->'runtime_result' ? 'duration_ms'
                    then ((refresh_event.raw_payload->'runtime_result'->>'duration_ms')::numeric)
                  else null
                end as duration_ms,
                case
                  when refresh_event.status = 'done'
                   and refresh_event.processed_at is not null
                    then greatest(extract(epoch from (refresh_event.processed_at - refresh_event.created_at)) * 1000, 0)
                  else null
                end as enqueue_to_fresh_ms,
                coalesce((refresh_event.raw_payload->'runtime_result'->>'skipped')::boolean, false) as skipped,
                refresh_event.raw_payload->'runtime_result'->>'skip_reason' as skip_reason
              from event_type_filter
              cross join lateral (
                select
                  id,
                  event_type,
                  aggregate_type,
                  aggregate_id,
                  scope_type,
                  scope_key,
                  payload,
                  raw_payload,
                  status,
                  source_version,
                  priority,
                  created_at,
                  processed_at,
                  updated_at
                from job.outbox_events
                where event_type = event_type_filter.event_type
                  and event_type like '%%.read_model.refresh'
                  and (
                    status in ('failed', 'dead_lettered')
                    or (
                      status = 'done'
                      and raw_payload->'runtime_result' ? 'duration_ms'
                    )
                  )
                order by updated_at desc
                limit %s
              ) refresh_event
            )
            select *
            from slow_refresh_event_samples
            order by
              greatest(coalesce(enqueue_to_fresh_ms, 0), coalesce(duration_ms, 0)) desc,
              updated_at desc,
              event_id
            limit %s
            """,
            (
                list(READ_MODEL_EVENT_TYPES.keys()),
                READ_MODEL_REFRESH_METRIC_SAMPLE_LIMIT,
                READ_MODEL_REFRESH_SLOW_EVENT_LIMIT,
            ),
        )
        current_slow_event_rows = self._connection.fetch_all(
            """
            with event_type_filter(event_type) as (
              select unnest(%s::text[])
            ),
            current_refresh_event_samples as (
              select
                refresh_event.id::text as event_id,
                refresh_event.event_type,
                coalesce(
                  refresh_event.scope_type,
                  refresh_event.payload->>'scope_type',
                  refresh_event.aggregate_type,
                  ''
                ) as scope_type,
                coalesce(
                  refresh_event.scope_key,
                  refresh_event.payload->>'scope_key',
                  refresh_event.aggregate_id,
                  ''
                ) as scope_key,
                refresh_event.status,
                refresh_event.source_version,
                refresh_event.priority,
                refresh_event.created_at::text as created_at,
                refresh_event.processed_at::text as processed_at,
                refresh_event.updated_at::text as updated_at,
                case
                  when refresh_event.status = 'done'
                   and refresh_event.raw_payload->'runtime_result' ? 'duration_ms'
                    then ((refresh_event.raw_payload->'runtime_result'->>'duration_ms')::numeric)
                  else null
                end as duration_ms,
                case
                  when refresh_event.status = 'done'
                   and refresh_event.processed_at is not null
                    then greatest(extract(epoch from (refresh_event.processed_at - refresh_event.created_at)) * 1000, 0)
                  else null
                end as enqueue_to_fresh_ms,
                coalesce((refresh_event.raw_payload->'runtime_result'->>'skipped')::boolean, false) as skipped,
                refresh_event.raw_payload->'runtime_result'->>'skip_reason' as skip_reason
              from event_type_filter
              cross join lateral (
                select
                  id,
                  event_type,
                  aggregate_type,
                  aggregate_id,
                  scope_type,
                  scope_key,
                  payload,
                  raw_payload,
                  status,
                  source_version,
                  priority,
                  created_at,
                  processed_at,
                  updated_at
                from job.outbox_events
                where event_type = event_type_filter.event_type
                  and event_type like '%%.read_model.refresh'
                  and created_at >= now() - interval '6 hours'
                  and (
                    status in ('failed', 'dead_lettered')
                    or (
                      status = 'done'
                      and raw_payload->'runtime_result' ? 'duration_ms'
                    )
                  )
                order by updated_at desc
                limit %s
              ) refresh_event
            )
            select *
            from current_refresh_event_samples
            order by
              greatest(coalesce(enqueue_to_fresh_ms, 0), coalesce(duration_ms, 0)) desc,
              duration_ms desc nulls last,
              updated_at desc,
              event_id
            limit %s
            """,
            (
                list(READ_MODEL_EVENT_TYPES.keys()),
                READ_MODEL_REFRESH_METRIC_SAMPLE_LIMIT,
                READ_MODEL_REFRESH_SLOW_EVENT_LIMIT,
            ),
        )
        refresh_duration_row: dict[str, Any] = {}
        refresh_failure_row: dict[str, Any] = {}
        read_model_refresh_by_key: list[dict[str, Any]] = []
        read_model_refresh_current_windows: dict[str, dict[str, Any]] = {
            window: _empty_refresh_metric_summary(window=window)
            for window in READ_MODEL_REFRESH_CURRENT_WINDOWS
        }
        read_model_refresh_by_key_current_windows: list[dict[str, Any]] = []
        for row in refresh_metric_rows:
            window_name = str(row.get("window_name") or "all_time")
            event_type = str(row.get("event_type") or "")
            if window_name != "all_time":
                if event_type == "__all__":
                    read_model_refresh_current_windows[window_name] = _refresh_metric_summary(row, window=window_name)
                    continue
                event_metadata = READ_MODEL_EVENT_TYPES.get(event_type)
                if event_metadata is None:
                    read_model_key = event_type
                    scope_type = event_type
                else:
                    read_model_key, scope_type = event_metadata
                read_model_refresh_by_key_current_windows.append(
                    {
                        "window": window_name,
                        "key": read_model_key,
                        "event_type": event_type,
                        "scope_type": scope_type,
                        **_refresh_metric_summary(row),
                    }
                )
                continue
            if event_type == "__all__":
                refresh_duration_row = dict(row)
                refresh_failure_row = dict(row)
                continue
            event_metadata = READ_MODEL_EVENT_TYPES.get(event_type)
            if event_metadata is None:
                read_model_key = event_type
                scope_type = event_type
            else:
                read_model_key, scope_type = event_metadata
            sample_count = _optional_int(row.get("read_model_refresh_total")) or 0
            failed_count = _optional_int(row.get("failed_count")) or 0
            read_model_refresh_by_key.append(
                {
                    "key": read_model_key,
                    "event_type": event_type,
                    "scope_type": scope_type,
                    "duration_ms": {
                        "p50": _optional_float(row.get("p50_ms")),
                        "p95": _optional_float(row.get("p95_ms")),
                        "p99": _optional_float(row.get("p99_ms")),
                    },
                    "enqueue_to_fresh_ms": {
                        "p50": _optional_float(row.get("enqueue_p50_ms")),
                        "p95": _optional_float(row.get("enqueue_p95_ms")),
                        "p99": _optional_float(row.get("enqueue_p99_ms")),
                    },
                    "sample_count": sample_count,
                    "completed_sample_count": _optional_int(row.get("completed_sample_count")) or 0,
                    "failed_count": failed_count,
                    "failure_rate": round(failed_count / sample_count, 6) if sample_count else 0.0,
                    "last_completed_at": row.get("last_completed_at"),
                    "last_fresh_at": row.get("last_fresh_at"),
                }
            )
        read_model_refresh_by_key.sort(
            key=lambda item: (
                item["duration_ms"]["p95"] is None,
                -float(item["duration_ms"]["p95"] or 0),
                str(item["key"]),
            )
        )
        read_model_refresh_by_key_current_windows.sort(
            key=lambda item: (
                str(item["window"]),
                item["enqueue_to_fresh_ms"]["p95"] is None,
                -float(item["enqueue_to_fresh_ms"]["p95"] or 0),
                str(item["key"]),
            )
        )
        read_model_refresh_slow_events = _read_model_refresh_slow_event_payloads(slow_event_rows)
        read_model_refresh_current_slow_events = _read_model_refresh_slow_event_payloads(current_slow_event_rows)
        publish_rows = self._connection.fetch_all(
            f"""
            select e.publish_status, count(*)::bigint as count
            from job.outbox_events e
            where e.status = 'pending'
              and e.event_type = any(%s)
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.publish_status
            order by e.publish_status
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        publish_lag_row = self._connection.fetch_one(
            f"""
            select extract(epoch from max(now() - e.created_at))::float as max_unpublished_age_seconds
            from job.outbox_events e
            where e.status = 'pending'
              and e.event_type = any(%s)
              and e.publish_status in ('unpublished', 'failed')
              and {_current_effective_outbox_attention_predicate_sql("e")}
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        publish_confirm_latency_row = self._connection.fetch_one(
            """
            with event_type_filter(event_type) as (
              select unnest(%s::text[])
            ),
            recent_publish_confirms as (
              select
                ((published_event.raw_payload->'rabbitmq_publish'->>'confirm_latency_ms')::numeric) as confirm_latency_ms
              from event_type_filter
              cross join lateral (
                select raw_payload, updated_at
                from job.outbox_events
                where event_type = event_type_filter.event_type
                  and publish_status = 'published'
                  and raw_payload->'rabbitmq_publish' ? 'confirm_latency_ms'
                order by updated_at desc
                limit %s
              ) published_event
            )
            select
              percentile_cont(0.5) within group (
                order by confirm_latency_ms
              )::float as p50_ms,
              percentile_cont(0.95) within group (
                order by confirm_latency_ms
              )::float as p95_ms,
              percentile_cont(0.99) within group (
                order by confirm_latency_ms
              )::float as p99_ms
            from recent_publish_confirms
            """,
            (list(_rabbitmq_dispatch_event_types()), RABBITMQ_PUBLISH_CONFIRM_METRIC_SAMPLE_LIMIT),
        )
        pending_outbox_by_scope = self._pending_outbox_events_by_scope()
        dirty_scopes_by_scope = self._dirty_scopes_by_scope()
        workbench_read_model = self._workbench_read_model_summary()
        queue_backlog = {str(row["status"]): int(row["count"]) for row in queue_rows}
        dirty_scopes = {str(row["status"]): int(row["count"]) for row in dirty_count_rows}
        publish_status = {str(row["publish_status"]): int(row["count"]) for row in publish_rows}
        stale_dirty_scopes = [
            {
                "tenant_id": row.get("tenant_id"),
                "scope_type": row.get("scope_type"),
                "scope_key": row.get("scope_key"),
                "status": row.get("status"),
                "age_seconds": row.get("age_seconds"),
                "attempts": row.get("attempts"),
                "last_error": row.get("last_error"),
            }
            for row in stale_rows
        ]
        max_pending_age_seconds = (age_row or {}).get("max_pending_age_seconds")
        total_refresh_count = int((refresh_failure_row or {}).get("read_model_refresh_total") or 0)
        failed_refresh_count = int((refresh_failure_row or {}).get("failed_count") or 0)
        rabbitmq_metrics = self._rabbitmq_metrics()
        worker_metrics = self.dashboard_worker_metrics()
        missing_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "required_worker_missing")
        stale_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "worker_heartbeat_stale")
        mismatched_required_worker_count = sum(
            1
            for row in worker_metrics
            if row.get("required") and row.get("warning_code") in {"worker_kind_mismatch", "worker_event_type_mismatch"}
        )
        return {
            "queue_backlog": queue_backlog,
            "dirty_scopes": dirty_scopes,
            "failed_jobs": int(queue_backlog.get("failed", 0)) + int(queue_backlog.get("dead_lettered", 0)),
            "max_pending_age_seconds": max_pending_age_seconds,
            "oldest_pending_event_age_seconds": max_pending_age_seconds,
            "worker_heartbeat_lag_seconds": (worker_lag_row or {}).get("max_worker_heartbeat_lag_seconds"),
            "worker_metrics": worker_metrics,
            "missing_required_worker_count": missing_required_worker_count,
            "stale_required_worker_count": stale_required_worker_count,
            "mismatched_required_worker_count": mismatched_required_worker_count,
            "read_model_refresh_duration_ms": {
                "p50": (refresh_duration_row or {}).get("p50_ms"),
                "p95": (refresh_duration_row or {}).get("p95_ms"),
                "p99": (refresh_duration_row or {}).get("p99_ms"),
            },
            "read_model_refresh_enqueue_to_fresh_ms": {
                "p50": (refresh_duration_row or {}).get("enqueue_p50_ms"),
                "p95": (refresh_duration_row or {}).get("enqueue_p95_ms"),
                "p99": (refresh_duration_row or {}).get("enqueue_p99_ms"),
            },
            "read_model_refresh_sample_count": total_refresh_count,
            "read_model_refresh_failure_rate": (
                round(failed_refresh_count / total_refresh_count, 6) if total_refresh_count else 0.0
            ),
            "read_model_refresh_by_key": read_model_refresh_by_key,
            "read_model_refresh_current_windows": read_model_refresh_current_windows,
            "read_model_refresh_by_key_current_windows": read_model_refresh_by_key_current_windows,
            "read_model_refresh_slow_events": read_model_refresh_slow_events,
            "read_model_refresh_current_slow_events": read_model_refresh_current_slow_events,
            "rabbitmq_publish_status": publish_status,
            "rabbitmq_unpublished_backlog": int(publish_status.get("unpublished", 0)),
            "rabbitmq_publish_failed_backlog": int(publish_status.get("failed", 0)),
            "rabbitmq_dispatcher_lag_seconds": (publish_lag_row or {}).get("max_unpublished_age_seconds"),
            "rabbitmq_publish_confirm_latency_ms": {
                "p50": (publish_confirm_latency_row or {}).get("p50_ms"),
                "p95": (publish_confirm_latency_row or {}).get("p95_ms"),
                "p99": (publish_confirm_latency_row or {}).get("p99_ms"),
            },
            "rabbitmq_publish_confirm_sample_limit": RABBITMQ_PUBLISH_CONFIRM_METRIC_SAMPLE_LIMIT,
            "rabbitmq_dispatch_event_types": list(_rabbitmq_dispatch_event_types()),
            **rabbitmq_metrics,
            "stale_dirty_scope_count": len(stale_dirty_scopes),
            "stale_dirty_scopes": stale_dirty_scopes,
            "pending_outbox_events_by_scope": pending_outbox_by_scope,
            "dirty_scopes_by_scope": dirty_scopes_by_scope,
            "workbench_read_model": workbench_read_model,
        }

    def ready_health_summary(self, *, stale_after_seconds: int = 300) -> dict[str, Any]:
        queue_rows = self._connection.fetch_all(
            f"""
            select e.status, count(*)::bigint as count
            from job.outbox_events e
            where e.status <> 'done'
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.status
            order by e.status
            """
        )
        age_row = self._connection.fetch_one(
            f"""
            select extract(epoch from max(now() - e.created_at))::float as max_pending_age_seconds
            from job.outbox_events e
            where e.status = 'pending'
              and {_current_effective_outbox_attention_predicate_sql("e")}
            """
        )
        dirty_count_rows = self._connection.fetch_all(
            """
            select status, count(*)::bigint as count
            from job.read_model_dirty_scopes
            group by status
            order by status
            """
        )
        stale_rows = self._connection.fetch_all(
            f"""
            select
              tenant_id,
              scope_type,
              scope_key,
              status,
              extract(epoch from now() - updated_at)::float as age_seconds,
              attempts,
              last_error,
              count(*) over()::bigint as total_count
            from job.read_model_dirty_scopes
            where status in ('pending', 'processing', 'failed')
              and updated_at < now() - (%s * interval '1 second')
              and {_current_effective_dirty_scope_predicate_sql()}
            order by updated_at, tenant_id, scope_type, scope_key
            limit 5
            """,
            (stale_after_seconds,),
        )
        worker_lag_row = self._connection.fetch_one(
            """
            with latest_worker_kind_heartbeats as (
              select distinct on (worker_kind)
                worker_kind,
                last_seen_at
              from job.runtime_worker_heartbeats
              order by worker_kind, last_seen_at desc
            )
            select extract(epoch from max(now() - last_seen_at))::float as max_worker_heartbeat_lag_seconds
            from latest_worker_kind_heartbeats
            where worker_kind <> 'runtime'
            """
        )
        refresh_failure_row = self._connection.fetch_one(
            f"""
            with event_type_filter(event_type) as (
              select unnest(%s::text[])
            ),
            recent_refresh_events as (
              select refresh_event.status
              from event_type_filter
              cross join lateral (
                select status, updated_at
                from job.outbox_events
                where event_type = event_type_filter.event_type
                  and event_type like '%%.read_model.refresh'
                  and {_CURRENT_EFFECTIVE_OUTBOX_EVENT_PREDICATE_SQL}
                  and (
                    status in ('failed', 'dead_lettered')
                    or (
                      status = 'done'
                      and raw_payload->'runtime_result' ? 'duration_ms'
                    )
                  )
                order by updated_at desc
                limit %s
              ) refresh_event
            )
            select
              count(*) filter (where status in ('failed', 'dead_lettered'))::bigint as failed_count,
              count(*)::bigint as read_model_refresh_total
            from recent_refresh_events
            """,
            (list(READ_MODEL_EVENT_TYPES.keys()), READ_MODEL_REFRESH_METRIC_SAMPLE_LIMIT),
        )
        publish_rows = self._connection.fetch_all(
            f"""
            select e.publish_status, count(*)::bigint as count
            from job.outbox_events e
            where e.status = 'pending'
              and e.event_type = any(%s)
              and {_current_effective_outbox_attention_predicate_sql("e")}
            group by e.publish_status
            order by e.publish_status
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        publish_lag_row = self._connection.fetch_one(
            f"""
            select extract(epoch from max(now() - e.created_at))::float as max_unpublished_age_seconds
            from job.outbox_events e
            where e.status = 'pending'
              and e.event_type = any(%s)
              and e.publish_status in ('unpublished', 'failed')
              and {_current_effective_outbox_attention_predicate_sql("e")}
            """,
            (list(_rabbitmq_dispatch_event_types()),),
        )
        pending_outbox_by_scope = self._pending_outbox_events_by_scope()
        dirty_scopes_by_scope = self._dirty_scopes_by_scope()
        queue_backlog = {str(row["status"]): int(row["count"]) for row in queue_rows}
        dirty_scopes = {str(row["status"]): int(row["count"]) for row in dirty_count_rows}
        publish_status = {str(row["publish_status"]): int(row["count"]) for row in publish_rows}
        stale_dirty_scopes = [
            {
                "tenant_id": row.get("tenant_id"),
                "scope_type": row.get("scope_type"),
                "scope_key": row.get("scope_key"),
                "status": row.get("status"),
                "age_seconds": row.get("age_seconds"),
                "attempts": row.get("attempts"),
                "last_error": row.get("last_error"),
            }
            for row in stale_rows
        ]
        total_refresh_count = int((refresh_failure_row or {}).get("read_model_refresh_total") or 0)
        failed_refresh_count = int((refresh_failure_row or {}).get("failed_count") or 0)
        worker_metrics = self.dashboard_worker_metrics()
        missing_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "required_worker_missing")
        stale_required_worker_count = sum(1 for row in worker_metrics if row.get("warning_code") == "worker_heartbeat_stale")
        mismatched_required_worker_count = sum(
            1
            for row in worker_metrics
            if row.get("required") and row.get("warning_code") in {"worker_kind_mismatch", "worker_event_type_mismatch"}
        )
        rabbitmq_metrics = self._rabbitmq_metrics()
        stale_dirty_scope_count = int(stale_rows[0].get("total_count") or len(stale_rows)) if stale_rows else 0
        max_pending_age_seconds = (age_row or {}).get("max_pending_age_seconds")
        return {
            "queue_backlog": queue_backlog,
            "dirty_scopes": dirty_scopes,
            "failed_jobs": int(queue_backlog.get("failed", 0)) + int(queue_backlog.get("dead_lettered", 0)),
            "max_pending_age_seconds": max_pending_age_seconds,
            "oldest_pending_event_age_seconds": max_pending_age_seconds,
            "worker_heartbeat_lag_seconds": (worker_lag_row or {}).get("max_worker_heartbeat_lag_seconds"),
            "worker_metrics": worker_metrics,
            "missing_required_worker_count": missing_required_worker_count,
            "stale_required_worker_count": stale_required_worker_count,
            "mismatched_required_worker_count": mismatched_required_worker_count,
            "read_model_refresh_sample_count": total_refresh_count,
            "read_model_refresh_failure_rate": (
                round(failed_refresh_count / total_refresh_count, 6) if total_refresh_count else 0.0
            ),
            "rabbitmq_publish_status": publish_status,
            "rabbitmq_unpublished_backlog": int(publish_status.get("unpublished", 0)),
            "rabbitmq_publish_failed_backlog": int(publish_status.get("failed", 0)),
            "rabbitmq_dispatcher_lag_seconds": (publish_lag_row or {}).get("max_unpublished_age_seconds"),
            **rabbitmq_metrics,
            "stale_dirty_scope_count": stale_dirty_scope_count,
            "stale_dirty_scopes": stale_dirty_scopes,
            "pending_outbox_events_by_scope": pending_outbox_by_scope,
            "dirty_scopes_by_scope": dirty_scopes_by_scope,
        }

    def _pending_outbox_events_by_scope(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            f"""
            with pending_outbox_by_scope as (
              select
                e.event_type,
                e.status,
                coalesce(e.scope_type, e.raw_payload->>'scope_type', e.aggregate_type, '') as scope_type,
                coalesce(e.scope_key, e.raw_payload->>'scope_key', e.aggregate_id, '') as scope_key,
                count(*)::bigint as count,
                extract(epoch from max(now() - e.created_at))::float as oldest_age_seconds,
                max(e.attempts)::integer as attempts,
                max(coalesce(e.last_error, '')) as last_error
              from job.outbox_events e
              where e.status in ('pending', 'processing', 'failed', 'dead_lettered')
                and {_current_effective_outbox_attention_predicate_sql("e")}
              group by 1, 2, 3, 4
              order by oldest_age_seconds desc nulls last, event_type, scope_type, scope_key
              limit 30
            )
            select * from pending_outbox_by_scope
            """
        )
        return [
            {
                "event_type": str(row.get("event_type") or ""),
                "status": str(row.get("status") or ""),
                "scope_type": str(row.get("scope_type") or ""),
                "scope_key": str(row.get("scope_key") or ""),
                "count": int(row.get("count") or 0),
                "oldest_age_seconds": row.get("oldest_age_seconds"),
                "attempts": int(row.get("attempts") or 0),
                "last_error": str(row.get("last_error") or ""),
            }
            for row in rows
        ]

    def _dirty_scopes_by_scope(self) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            f"""
            with dirty_scope_backlog_by_scope as (
              select
                scope_type,
                scope_key,
                status,
                count(*)::bigint as count,
                extract(epoch from max(now() - updated_at))::float as oldest_age_seconds,
                max(attempts)::integer as attempts,
                max(coalesce(last_error, '')) as last_error
              from job.read_model_dirty_scopes
              where status in ('pending', 'processing', 'failed')
                and {_current_effective_dirty_scope_predicate_sql()}
              group by scope_type, scope_key, status
              order by oldest_age_seconds desc nulls last, scope_type, scope_key
              limit 30
            )
            select * from dirty_scope_backlog_by_scope
            """
        )
        return [
            {
                "scope_type": str(row.get("scope_type") or ""),
                "scope_key": str(row.get("scope_key") or ""),
                "status": str(row.get("status") or ""),
                "count": int(row.get("count") or 0),
                "oldest_age_seconds": row.get("oldest_age_seconds"),
                "attempts": int(row.get("attempts") or 0),
                "last_error": str(row.get("last_error") or ""),
            }
            for row in rows
        ]

    def _workbench_read_model_summary(self) -> dict[str, Any]:
        generation_rows = self._connection.fetch_all(
            """
            with workbench_generation_status_counts as (
              select status, count(*)::bigint as count
              from read_model.workbench_generations
              where tenant_id = 'default'
                and status in ('active', 'building', 'failed')
              group by status
              order by status
            )
            select * from workbench_generation_status_counts
            """
        )
        active_rows = self._connection.fetch_all(
            """
            with workbench_active_generation_totals as (
              select
                count(*)::bigint as active_scope_count,
                coalesce(sum(row_count), 0)::bigint as active_row_count,
                coalesce(sum(group_count), 0)::bigint as active_group_count,
                coalesce(sum(summary_count), 0)::bigint as active_summary_count,
                max(activated_at)::text as latest_generated_at
              from read_model.workbench_generations
              where tenant_id = 'default'
                and status = 'active'
            )
            select * from workbench_active_generation_totals
            """
        )
        all_scope_row = self._connection.fetch_one(
            """
            select
              status,
              row_count,
              group_count,
              summary_count,
              updated_at::text as updated_at,
              coalesce(last_error, '') as last_error
            from read_model.workbench_generations workbench_all_scope_generation
            where tenant_id = 'default'
              and scope_key = 'all'
              and status in ('active', 'building', 'failed')
            order by
              case status when 'active' then 0 when 'building' then 1 else 2 end,
              updated_at desc
            limit 1
            """
        )
        status_counts = {str(row.get("status") or ""): int(row.get("count") or 0) for row in generation_rows}
        active_totals = active_rows[0] if active_rows else {}
        return {
            "generation_status_counts": status_counts,
            "active_scope_count": int(active_totals.get("active_scope_count") or 0),
            "active_row_count": int(active_totals.get("active_row_count") or 0),
            "active_group_count": int(active_totals.get("active_group_count") or 0),
            "active_summary_count": int(active_totals.get("active_summary_count") or 0),
            "building_scope_count": int(status_counts.get("building", 0)),
            "failed_scope_count": int(status_counts.get("failed", 0)),
            "latest_generated_at": active_totals.get("latest_generated_at"),
            "all_scope": {
                "status": str((all_scope_row or {}).get("status") or ""),
                "row_count": int((all_scope_row or {}).get("row_count") or 0),
                "group_count": int((all_scope_row or {}).get("group_count") or 0),
                "summary_count": int((all_scope_row or {}).get("summary_count") or 0),
                "updated_at": (all_scope_row or {}).get("updated_at"),
                "last_error": str((all_scope_row or {}).get("last_error") or ""),
            },
        }

    def _rabbitmq_metrics(self) -> dict[str, Any]:
        provider = self._rabbitmq_metrics_provider
        if provider is None:
            try:
                from fin_ops_platform.services.rabbitmq_runtime import RabbitMqManagementMetrics
                from fin_ops_platform.services.runtime_queue import RuntimeQueueSettings

                provider = RabbitMqManagementMetrics(RuntimeQueueSettings.from_env())
            except Exception as exc:
                return {"rabbitmq_metric_error": str(exc) or exc.__class__.__name__}
        summary = provider.summary()
        return summary if isinstance(summary, dict) else {}

    def dashboard_outbox_metric(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            f"""
            with dashboard_outbox_attention_events as (
              select
                e.status,
                e.publish_status,
                e.created_at
              from job.outbox_events e
              where e.status in ('pending', 'failed', 'dead_lettered')
                and {_current_effective_outbox_attention_predicate_sql("e")}
              union all
              select
                e.status,
                e.publish_status,
                e.created_at
              from job.outbox_events e
              where e.publish_status = 'publishing'
                and e.status not in ('pending', 'failed', 'dead_lettered')
                and {_current_effective_outbox_attention_predicate_sql("e")}
            )
            select
              count(*) filter (where status = 'pending')::bigint as pending_count,
              count(*) filter (where publish_status = 'publishing')::bigint as publishing_count,
              count(*) filter (where status in ('failed', 'dead_lettered'))::bigint as failed_count,
              count(*) filter (where publish_status = 'failed')::bigint as publish_failed_count,
              extract(epoch from max(now() - created_at) filter (where status = 'pending'))::float
                as oldest_pending_age_seconds
            from dashboard_outbox_attention_events
            """
        ) or {}
        return {
            "pending_count": _optional_int(row.get("pending_count")),
            "publishing_count": _optional_int(row.get("publishing_count")),
            "failed_count": _optional_int(row.get("failed_count")),
            "publish_failed_count": _optional_int(row.get("publish_failed_count")),
            "oldest_pending_age_seconds": _optional_float(row.get("oldest_pending_age_seconds")),
            "status": "available",
        }

    def dashboard_queue_metrics(self) -> list[dict[str, Any]]:
        settings = RuntimeQueueSettings.from_env()
        routes = rabbitmq_event_routes(settings)
        summary = self._rabbitmq_metrics()
        queues = summary.get("rabbitmq_queues") if isinstance(summary, dict) else None
        metric_error = summary.get("rabbitmq_metric_error") if isinstance(summary, dict) else None
        metrics_available = isinstance(queues, dict) and not metric_error
        rows: list[dict[str, Any]] = []
        for event_type, route in routes.items():
            queue_metric = queues.get(event_type) if metrics_available else None
            queue_payload = queue_metric if isinstance(queue_metric, dict) else {}
            if metrics_available:
                rows.append(
                    {
                        "event_type": event_type,
                        "queue": route.queue,
                        "messages": _optional_int(queue_payload.get("messages")),
                        "unacked": _optional_int(queue_payload.get("unacked")),
                        "consumers": _optional_int(queue_payload.get("consumers")),
                        "dlq_messages": _optional_int(queue_payload.get("dead_letter_messages")),
                        "status": "available",
                    }
                )
            else:
                rows.append(
                    {
                        "event_type": event_type,
                        "queue": route.queue,
                        "messages": None,
                        "unacked": None,
                        "consumers": None,
                        "dlq_messages": None,
                        "status": "unknown",
                        "warning_code": "rabbitmq_metrics_unavailable",
                    }
                )
        return rows

    def dashboard_read_model_metrics(self) -> list[dict[str, Any]]:
        event_types = tuple(READ_MODEL_EVENT_TYPES.keys())
        duration_rows = self._connection.fetch_all(
            """
            with event_type_filter(event_type) as (
              select unnest(%s::text[])
            ),
            refresh_events as (
              select
                refresh_event.event_type,
                refresh_event.updated_at,
                case
                  when refresh_event.metric_scope_key = 'all'
                    then 'full'
                  when refresh_event.metric_scope_key ~ '^\\d{4}-\\d{2}$'
                    then 'incremental'
                  else 'unknown'
                end as refresh_kind,
                refresh_event.duration_ms
              from event_type_filter
              cross join lateral (
                select
                  event_type,
                  updated_at,
                  coalesce(aggregate_id, raw_payload->>'scope_key', raw_payload->'runtime_result'->>'scope_key', '') as metric_scope_key,
                  ((raw_payload->'runtime_result'->>'duration_ms')::numeric) as duration_ms
                from job.outbox_events
                where event_type = event_type_filter.event_type
                  and event_type like '%%.read_model.refresh'
                  and status = 'done'
                  and raw_payload->'runtime_result' ? 'duration_ms'
                order by updated_at desc
                limit %s
              ) refresh_event
            ),
            metric_windows(window_name, started_at) as (
              values
                ('recent_15m', now() - interval '15 minutes'),
                ('recent_1h', now() - interval '1 hour'),
                ('all_time', '-infinity'::timestamptz)
            )
            select
              event_type,
              window_name,
              refresh_kind,
              count(*)::bigint as sample_count,
              max(updated_at)::text as last_completed_at,
              percentile_cont(0.5) within group (
                order by duration_ms
              )::float as p50_ms,
              percentile_cont(0.95) within group (
                order by duration_ms
              )::float as p95_ms,
              percentile_cont(0.99) within group (
                order by duration_ms
              )::float as p99_ms
            from refresh_events
            join metric_windows
              on refresh_events.updated_at >= metric_windows.started_at
            group by event_type, window_name, refresh_kind
            """,
            (list(event_types), READ_MODEL_REFRESH_METRIC_SAMPLE_LIMIT),
        )
        dirty_rows = self._connection.fetch_all(
            """
            select
              scope_type,
              count(*) filter (where status in ('pending', 'processing', 'failed'))::bigint as stale_count,
              count(*) filter (where status = 'failed')::bigint as unavailable_count
            from job.read_model_dirty_scopes
            where scope_type = any(%s)
              and status in ('pending', 'processing', 'failed')
            group by scope_type
            """,
            (list({scope_type for _, scope_type in READ_MODEL_EVENT_TYPES.values()}),),
        )
        workbench_consistency_unavailable_count = 0
        workbench_consistency_warning: str | None = None
        try:
            consistency_row = self._connection.fetch_one(
                """
                select count(*)::bigint as inconsistent_count
                from read_model.workbench_generations
                where tenant_id = 'default'
                  and status = 'active'
                  and consistency_status = 'inconsistent'
                """
            )
            workbench_consistency_unavailable_count = _optional_int(
                (consistency_row or {}).get("inconsistent_count")
            ) or 0
        except Exception:
            workbench_consistency_warning = "workbench_generation_consistency_unavailable"
        durations_by_event_type: dict[str, dict[str, Any]] = {}
        for row in duration_rows:
            event_type = str(row.get("event_type") or "")
            if not event_type:
                continue
            window_name = str(row.get("window_name") or "all_time")
            refresh_kind = str(row.get("refresh_kind") or "unknown")
            event_payload = durations_by_event_type.setdefault(event_type, {"windows": {}, "kinds": {}})
            window_payload = event_payload["windows"].setdefault(
                window_name,
                {
                    "sample_count": 0,
                    "last_completed_at": None,
                    "duration_ms": dict(EMPTY_PERCENTILES),
                },
            )
            sample_count = _optional_int(row.get("sample_count")) or 0
            if sample_count > int(window_payload["sample_count"]):
                window_payload["sample_count"] = sample_count
                window_payload["last_completed_at"] = row.get("last_completed_at")
                window_payload["duration_ms"] = {
                    "p50": _optional_float(row.get("p50_ms")),
                    "p95": _optional_float(row.get("p95_ms")),
                    "p99": _optional_float(row.get("p99_ms")),
                }
            event_payload["kinds"].setdefault(refresh_kind, {})[window_name] = {
                "sample_count": sample_count,
                "last_completed_at": row.get("last_completed_at"),
                "duration_ms": {
                    "p50": _optional_float(row.get("p50_ms")),
                    "p95": _optional_float(row.get("p95_ms")),
                    "p99": _optional_float(row.get("p99_ms")),
                },
            }
        dirty_by_scope_type = {str(row.get("scope_type")): row for row in dirty_rows}
        rows: list[dict[str, Any]] = []
        for event_type, (key, scope_type) in READ_MODEL_EVENT_TYPES.items():
            duration = durations_by_event_type.get(event_type, {})
            windows = duration.get("windows") if isinstance(duration.get("windows"), dict) else {}
            recent_15m = windows.get("recent_15m") if isinstance(windows.get("recent_15m"), dict) else {}
            all_time = windows.get("all_time") if isinstance(windows.get("all_time"), dict) else {}
            dirty = dirty_by_scope_type.get(scope_type, {})
            unavailable_count = _optional_int(dirty.get("unavailable_count")) or 0
            warning_code = None
            if key == "workbench":
                unavailable_count += workbench_consistency_unavailable_count
                warning_code = workbench_consistency_warning
            rows.append(
                {
                    "key": key,
                    "refresh_duration_ms": recent_15m.get("duration_ms") or dict(EMPTY_PERCENTILES),
                    "refresh_duration_windows": {
                        "recent_15m": recent_15m
                        or {"sample_count": 0, "last_completed_at": None, "duration_ms": dict(EMPTY_PERCENTILES)},
                        "recent_1h": windows.get("recent_1h")
                        or {"sample_count": 0, "last_completed_at": None, "duration_ms": dict(EMPTY_PERCENTILES)},
                    },
                    "historical_refresh_duration_ms": all_time.get("duration_ms") or dict(EMPTY_PERCENTILES),
                    "refresh_duration_by_kind": duration.get("kinds") if isinstance(duration.get("kinds"), dict) else {},
                    "stale_count": _optional_int(dirty.get("stale_count")) or 0,
                    "unavailable_count": unavailable_count,
                    "status": "available",
                    **({"warning_code": warning_code} if warning_code else {}),
                }
            )
        return rows

    def dashboard_worker_metrics(
        self,
        *,
        worker_instances: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_instances = {
            str(instance).strip()
            for instance in set(worker_instances or set())
            if str(instance).strip()
        }
        registrations = worker_registrations(required_only=True)
        if worker_instances is not None:
            registrations = [
                registration
                for registration in registrations
                if registration.instance_name in normalized_instances
            ]
        worker_kinds = sorted({registration.worker_kind for registration in registrations})
        worker_filter_sql = ""
        worker_filter_params: tuple[object, ...] = ()
        if worker_instances is not None:
            worker_filter_sql = """
              and (
                coalesce(payload->>'worker_instance', worker_kind) = any(%s::text[])
                or worker_kind = any(%s::text[])
              )
            """
            worker_filter_params = (sorted(normalized_instances), worker_kinds)
        rows = self._connection.fetch_all(
            f"""
            select distinct on (coalesce(payload->>'worker_instance', worker_kind))
              worker_id,
              coalesce(payload->>'worker_instance', worker_kind) as worker_instance,
              worker_kind,
              status,
              extract(epoch from now() - last_seen_at)::float as heartbeat_lag_seconds,
              payload
            from job.runtime_worker_heartbeats
            where worker_kind <> 'runtime'
              {worker_filter_sql}
            order by coalesce(payload->>'worker_instance', worker_kind), last_seen_at desc
            """,
            worker_filter_params,
        )
        latest_by_instance: dict[str, dict[str, Any]] = {}
        latest_by_kind: dict[str, dict[str, Any]] = {}
        for row in rows:
            worker_instance = str(row.get("worker_instance") or "").strip()
            worker_kind = str(row.get("worker_kind") or "").strip()
            if worker_instance:
                latest_by_instance[worker_instance] = row
            if worker_kind and worker_kind not in latest_by_kind:
                latest_by_kind[worker_kind] = row
        registrations_by_kind = registration_by_worker_kind()
        worker_rows: list[dict[str, Any]] = []
        emitted_instances: set[str] = set()
        emitted_worker_ids: set[str] = set()
        for registration in registrations:
            row = latest_by_instance.get(registration.instance_name) or latest_by_kind.get(registration.worker_kind)
            emitted_instances.add(registration.instance_name)
            if row is None:
                worker_rows.append(
                    {
                        "worker_id": "",
                        "worker_instance": registration.instance_name,
                        "worker_kind": registration.worker_kind,
                        "expected_worker_kind": registration.worker_kind,
                        "worker_status": "missing",
                        "heartbeat_lag_seconds": None,
                        "required": True,
                        "expected_event_types": list(registration.event_types),
                        "expected_transport": "rabbitmq_or_postgres" if registration.rabbitmq_eligible else "postgres",
                        "status": "missing",
                        "warning_code": "required_worker_missing",
                    }
                )
                continue
            worker_id = str(row.get("worker_id") or "").strip()
            if worker_id:
                emitted_worker_ids.add(worker_id)
            worker_rows.append(_worker_metric_row(row, registration=registration, required=True))
        for row in rows:
            worker_instance = str(row.get("worker_instance") or "").strip()
            if worker_instances is not None and worker_instance not in normalized_instances:
                continue
            if worker_instance in emitted_instances:
                continue
            worker_id = str(row.get("worker_id") or "").strip()
            if worker_id and worker_id in emitted_worker_ids:
                continue
            worker_kind = str(row.get("worker_kind") or "unknown")
            registration = registrations_by_kind.get(worker_kind)
            worker_rows.append(_worker_metric_row(row, registration=registration, required=False))
        return worker_rows


def _rabbitmq_dispatch_event_types() -> tuple[str, ...]:
    try:
        return RuntimeQueueSettings.from_env().rabbitmq_dispatch_event_types
    except Exception:
        return DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_payload(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _normalized_operation_barrier_targets(targets: list[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for target in list(targets or []):
        if not isinstance(target, dict):
            continue
        read_model_key = str(target.get("read_model_key") or "").strip().lower()
        definition = APP_STATUS_READ_MODEL_REGISTRY.get(read_model_key)
        scope_type = str(
            target.get("scope_type")
            or (definition.scope_type if definition is not None else read_model_key)
            or ""
        ).strip()
        scope_key = str(target.get("scope_key") or "all").strip() or "all"
        identity = (read_model_key, scope_type, scope_key)
        if not read_model_key or identity in seen:
            continue
        seen.add(identity)
        normalized.append(
            {
                "read_model_key": read_model_key,
                "scope_type": scope_type,
                "scope_key": scope_key,
                "refresh_event_type": definition.refresh_event_type if definition is not None else "",
                "worker_instance": definition.worker_instance if definition is not None else "",
            }
        )
    return normalized


def _operation_barrier_scope_filter_sql(
    targets: list[dict[str, str]] | None,
    *,
    read_model_key_sql: str | None,
    scope_type_sql: str,
    scope_key_sql: str,
    event_type_sql: str | None = None,
) -> tuple[str, tuple[object, ...]]:
    if targets is None:
        return "", ()
    key_sql = event_type_sql or read_model_key_sql
    if key_sql is None:
        target_keys = [target["scope_type"] for target in targets]
        key_sql = scope_type_sql
    else:
        target_keys = [target["refresh_event_type" if event_type_sql is not None else "read_model_key"] for target in targets]
    target_scope_types = [target["scope_type"] for target in targets]
    target_scope_keys = [target["scope_key"] for target in targets]
    return (
        f"""
and exists (
  select 1
  from unnest(%s::text[], %s::text[], %s::text[])
       as barrier_target(target_key, target_scope_type, target_scope_key)
  where barrier_target.target_key = coalesce({key_sql}, '')
    and barrier_target.target_scope_type = coalesce({scope_type_sql}, '')
    and (
      barrier_target.target_scope_key = coalesce({scope_key_sql}, '')
      or (
        barrier_target.target_scope_key <> 'all'
        and coalesce({scope_key_sql}, '') = 'all'
      )
    )
)
""",
        (target_keys, target_scope_types, target_scope_keys),
    )


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _refresh_metric_summary(row: dict[str, Any], *, window: str | None = None) -> dict[str, Any]:
    sample_count = _optional_int(row.get("read_model_refresh_total")) or 0
    failed_count = _optional_int(row.get("failed_count")) or 0
    payload: dict[str, Any] = {
        "duration_ms": {
            "p50": _optional_float(row.get("p50_ms")),
            "p95": _optional_float(row.get("p95_ms")),
            "p99": _optional_float(row.get("p99_ms")),
        },
        "enqueue_to_fresh_ms": {
            "p50": _optional_float(row.get("enqueue_p50_ms")),
            "p95": _optional_float(row.get("enqueue_p95_ms")),
            "p99": _optional_float(row.get("enqueue_p99_ms")),
        },
        "sample_count": sample_count,
        "completed_sample_count": _optional_int(row.get("completed_sample_count")) or 0,
        "failed_count": failed_count,
        "failure_rate": round(failed_count / sample_count, 6) if sample_count else 0.0,
        "last_completed_at": row.get("last_completed_at"),
        "last_fresh_at": row.get("last_fresh_at"),
    }
    if window is not None:
        payload["window"] = window
    return payload


def _empty_refresh_metric_summary(*, window: str) -> dict[str, Any]:
    return {
        "window": window,
        "duration_ms": dict(EMPTY_PERCENTILES),
        "enqueue_to_fresh_ms": dict(EMPTY_PERCENTILES),
        "sample_count": 0,
        "completed_sample_count": 0,
        "failed_count": 0,
        "failure_rate": 0.0,
        "last_completed_at": None,
        "last_fresh_at": None,
    }


def _read_model_refresh_slow_event_payloads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for row in rows:
        event_type = str(row.get("event_type") or "")
        event_metadata = READ_MODEL_EVENT_TYPES.get(event_type)
        if event_metadata is None:
            read_model_key = event_type
        else:
            read_model_key, _scope_type = event_metadata
        payloads.append(
            {
                "event_id": str(row.get("event_id") or ""),
                "key": read_model_key,
                "event_type": event_type,
                "scope_type": str(row.get("scope_type") or ""),
                "scope_key": str(row.get("scope_key") or ""),
                "status": str(row.get("status") or ""),
                "source_version": _optional_int(row.get("source_version")),
                "priority": str(row.get("priority") or ""),
                "duration_ms": _optional_float(row.get("duration_ms")),
                "enqueue_to_fresh_ms": _optional_float(row.get("enqueue_to_fresh_ms")),
                "created_at": row.get("created_at"),
                "processed_at": row.get("processed_at"),
                "updated_at": row.get("updated_at"),
                "skipped": bool(row.get("skipped")),
                "skip_reason": str(row.get("skip_reason") or ""),
            }
        )
    return payloads


def _app_status_dirty_scope_status(value: object) -> str:
    status = str(value or "").strip()
    if status == "failed":
        return "failed"
    if status in {"pending", "processing"}:
        return "refreshing"
    return "ready"


def _app_status_read_model_scope_payload(
    *,
    read_model_key: object,
    scope_type: object,
    scope_key: object,
    status: object,
    last_error: object,
    updated_at: object,
) -> dict[str, str]:
    return {
        "read_model_key": str(read_model_key or "").strip(),
        "scope_type": str(scope_type or "").strip(),
        "scope_key": str(scope_key or "").strip(),
        "status": str(status or "missing").strip().lower() or "missing",
        "last_error": str(last_error or "").strip(),
        "updated_at": str(updated_at or "").strip(),
    }


def _upsert_app_status_read_model_scope(scopes: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    scope_identity = (
        str(payload.get("read_model_key") or "").strip(),
        str(payload.get("scope_type") or "").strip(),
        str(payload.get("scope_key") or "").strip(),
    )
    for existing in scopes:
        existing_identity = (
            str(existing.get("read_model_key") or "").strip(),
            str(existing.get("scope_type") or "").strip(),
            str(existing.get("scope_key") or "").strip(),
        )
        if existing_identity != scope_identity:
            continue
        merged_status = _merge_app_status_read_model_scope_status(
            str(existing.get("status") or ""),
            str(payload.get("status") or ""),
        )
        existing["status"] = merged_status
        existing["updated_at"] = _latest_text(existing.get("updated_at"), payload.get("updated_at"))
        if merged_status == "refreshing":
            existing["last_error"] = ""
        elif payload.get("last_error"):
            existing["last_error"] = str(payload.get("last_error") or "").strip()
        return
    scopes.append(payload)


def _merge_app_status_read_model_scope_status(left: str, right: str) -> str:
    normalized_left = str(left or "").strip().lower()
    normalized_right = str(right or "").strip().lower()
    if "refreshing" in {normalized_left, normalized_right}:
        return "refreshing"
    return _max_app_status(normalized_left or "missing", normalized_right or "missing")


def _app_status_status_from_scopes(scopes: list[dict[str, Any]], *, fallback: str) -> str:
    status = str(fallback or "missing").strip().lower() or "missing"
    if not scopes:
        return status
    status = "ready"
    for scope in scopes:
        status = _max_app_status(status, str(scope.get("status") or "missing").strip().lower() or "missing")
    return status


def _app_status_last_error_from_scopes(scopes: list[dict[str, Any]]) -> str:
    for scope in scopes:
        if str(scope.get("status") or "").strip().lower() not in {"failed", "unavailable"}:
            continue
        error = str(scope.get("last_error") or "").strip()
        if error:
            return error
    return ""


def _latest_text(left: object, right: object) -> str:
    left_text = str(left or "").strip()
    right_text = str(right or "").strip()
    if not left_text:
        return right_text
    if not right_text:
        return left_text
    return right_text if right_text > left_text else left_text


def _app_status_historical_read_model_scope_payload(
    *,
    read_model_key: object,
    scope_type: object,
    scope_key: object,
    status: object,
    last_error: object,
    updated_at: object,
    history_reason: str,
) -> dict[str, Any]:
    payload = _app_status_read_model_scope_payload(
        read_model_key=read_model_key,
        scope_type=scope_type,
        scope_key=scope_key,
        status=status,
        last_error=last_error,
        updated_at=updated_at,
    )
    payload["current_effective"] = False
    payload["history_reason"] = history_reason
    return payload


def _is_legacy_cost_statistics_scope(scope_type: object, scope_key: object) -> bool:
    if str(scope_type or "").strip() != "cost_statistics":
        return False
    key = str(scope_key or "").strip()
    if key == "all":
        return True
    parts = key.split("-")
    return len(parts) == 2 and len(parts[0]) == 4 and len(parts[1]) == 2 and all(part.isdigit() for part in parts)


def _is_historical_outbox_status(row: dict[str, Any]) -> bool:
    if _is_legacy_cost_statistics_scope(row.get("scope_type"), row.get("scope_key")):
        return True
    entry = READ_MODEL_MANIFEST_BY_EVENT_TYPE.get(str(row.get("event_type") or "").strip())
    command_only_parent = bool(
        entry is not None
        and is_command_only_read_model_scope(entry.key, str(row.get("scope_key") or ""))
    )
    return (
        _truthy(row.get("covered_by_later_event"))
        or _truthy(row.get("covered_by_later_done"))
        or (_truthy(row.get("covered_by_later_readiness")) and not command_only_parent)
        or _truthy(row.get("covered_by_active_dirty_scope"))
    )


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "t", "true", "yes", "y"}


def _max_app_status(left: str, right: str) -> str:
    rank = {
        "ready": 0,
        "fresh": 0,
        "refreshing": 1,
        "missing": 1,
        "stale": 2,
        "schema_mismatch": 2,
        "source_mismatch": 2,
        "failed": 3,
        "unavailable": 4,
    }
    return right if rank.get(right, 0) > rank.get(left, 0) else left


def _max_app_outbox_status(left: str, right: str) -> str:
    normalized = "failed" if right in {"publish_failed", "failed", "dead_lettered"} else right
    normalized = "publishing" if normalized == "processing" else normalized
    rank = {"ready": 0, "pending": 1, "publishing": 2, "failed": 3}
    return normalized if rank.get(normalized, 0) > rank.get(left, 0) else left


def _app_status_worker_status(value: object) -> str:
    status = str(value or "").strip()
    if status == "available":
        return "ready"
    if status in {"missing", "mismatch"}:
        return "unavailable"
    if status == "stale":
        return "stale"
    return status or "ready"


def _worker_metric_row(
    row: dict[str, Any],
    *,
    registration: Any | None,
    required: bool,
) -> dict[str, Any]:
    heartbeat_lag_seconds = _optional_float(row.get("heartbeat_lag_seconds"))
    worker_instance = str(row.get("worker_instance") or "")
    worker_kind = str(row.get("worker_kind") or "unknown")
    payload_value = row.get("payload")
    heartbeat_payload = payload_value if isinstance(payload_value, dict) else {}
    configured_event_types = _string_list(heartbeat_payload.get("configured_event_types"))
    expected_event_types = list(registration.event_types) if registration is not None else []
    stale_after_seconds = (
        int(registration.heartbeat_stale_after_seconds)
        if registration is not None
        else None
    )
    is_stale = (
        required
        and heartbeat_lag_seconds is not None
        and stale_after_seconds is not None
        and heartbeat_lag_seconds > stale_after_seconds
    )
    current_effective = required or not (
        heartbeat_lag_seconds is not None
        and stale_after_seconds is not None
        and heartbeat_lag_seconds > stale_after_seconds
    )
    warning_code = None
    if registration is not None and worker_kind != registration.worker_kind:
        warning_code = "worker_kind_mismatch"
    elif registration is not None and configured_event_types and tuple(configured_event_types) not in {
        tuple(registration.event_types),
        registration.claim_event_types(transport="postgres"),
        registration.claim_event_types(transport="rabbitmq"),
    }:
        warning_code = "worker_event_type_mismatch"
    elif is_stale:
        warning_code = "worker_heartbeat_stale"
    payload = {
        "worker_id": str(row.get("worker_id") or ""),
        "worker_instance": worker_instance,
        "worker_kind": worker_kind,
        "expected_worker_kind": registration.worker_kind if registration is not None else worker_kind,
        "worker_status": str(row.get("status") or ""),
        "heartbeat_lag_seconds": heartbeat_lag_seconds,
        "heartbeat_stale_after_seconds": stale_after_seconds,
        "current_effective": current_effective,
        "required": required,
        "expected_event_types": expected_event_types,
        "configured_event_types": configured_event_types,
        "expected_transport": (
            "rabbitmq_or_postgres"
            if registration is not None and registration.rabbitmq_eligible
            else "postgres"
            if registration is not None
            else "unknown"
        ),
        "status": "stale" if is_stale else "mismatch" if warning_code else "available",
    }
    if warning_code:
        payload["warning_code"] = warning_code
    return payload


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _app_status_readiness_backfill_fact(connection: Any, read_model_key: str, *, tenant_id: str) -> dict[str, Any] | None:
    if read_model_key == "workbench":
        return connection.fetch_one(
            """
            select
                'all' as scope_key,
                case status when 'active' then 'fresh' when 'failed' then 'failed' else 'missing' end as status,
                row_count,
                schema_version,
                source_versions,
                activated_at::text as generated_at,
                last_error
            from read_model.workbench_generations
            where tenant_id = %s
              and scope_key = 'all'
            order by case status when 'active' then 0 when 'failed' then 1 else 2 end, updated_at desc
            limit 1
            """,
            (tenant_id,),
        )
    scope_spec = APP_STATUS_READINESS_BACKFILL_SCOPE_TABLES.get(read_model_key)
    if scope_spec:
        tenant_where = "tenant_id = %s" if scope_spec["tenant_scoped"] else "true"
        params = (tenant_id,) if scope_spec["tenant_scoped"] else ()
        return connection.fetch_one(
            f"""
            select
                scope_key,
                {scope_spec["status_expr"]} as status,
                row_count,
                {scope_spec["schema_expr"]} as schema_version,
                source_versions,
                generated_at::text as generated_at,
                {scope_spec["last_error_expr"]} as last_error
            from {scope_spec["table"]}
            where {tenant_where}
            order by case {scope_spec["status_expr"]} when 'fresh' then 0 else 1 end,
                     generated_at desc nulls last,
                     updated_at desc
            limit 1
            """,
            params,
        )
    if read_model_key == "bank_account_balance":
        return connection.fetch_one(
            """
            select
                'all' as scope_key,
                'fresh' as status,
                count(*)::integer as row_count,
                max(schema_version)::text as schema_version,
                coalesce((array_agg(source_versions order by generated_at desc))[1], '{}'::jsonb) as source_versions,
                max(generated_at)::text as generated_at,
                '' as last_error
            from read_model.bank_account_balances
            where tenant_id = %s
            having count(*) >= 0 and max(generated_at) is not null
            """,
            (tenant_id,),
        )
    row_spec = APP_STATUS_READINESS_BACKFILL_ROW_TABLES.get(read_model_key)
    if row_spec:
        return connection.fetch_one(
            f"""
            select
                'all' as scope_key,
                {row_spec["status_expr"]} as status,
                count(*)::integer as row_count,
                {row_spec["schema_expr"]} as schema_version,
                coalesce((array_agg(source_versions order by generated_at desc))[1], '{{}}'::jsonb) as source_versions,
                max(generated_at)::text as generated_at,
                '' as last_error
            from {row_spec["table"]}
            having count(*) >= 0 and max(generated_at) is not null
            """
        )
    return None


APP_STATUS_READINESS_BACKFILL_SCOPE_TABLES = {
    "bank_detail": {
        "table": "read_model.bank_detail_scopes",
        "tenant_scoped": True,
        "status_expr": "coalesce(nullif(status, ''), 'fresh')",
        "schema_expr": "coalesce(schema_version::text, '')",
        "last_error_expr": "coalesce(last_error, '')",
    },
    "workbench_relation": {
        "table": "read_model.workbench_relation_scopes",
        "tenant_scoped": True,
        "status_expr": "coalesce(nullif(cache_status, ''), 'fresh')",
        "schema_expr": "''",
        "last_error_expr": "''",
    },
    "invoice_lifecycle": {
        "table": "read_model.invoice_lifecycle_scopes",
        "tenant_scoped": True,
        "status_expr": "coalesce(nullif(cache_status, ''), 'fresh')",
        "schema_expr": "''",
        "last_error_expr": "''",
    },
    "input_invoice_usage": {
        "table": "read_model.input_invoice_usage_scopes",
        "tenant_scoped": False,
        "status_expr": "coalesce(nullif(cache_status, ''), 'fresh')",
        "schema_expr": "''",
        "last_error_expr": "''",
    },
    "output_invoice_collection": {
        "table": "read_model.output_invoice_collection_scopes",
        "tenant_scoped": False,
        "status_expr": "coalesce(nullif(cache_status, ''), 'fresh')",
        "schema_expr": "''",
        "last_error_expr": "''",
    },
    "oa_pending_payment": {
        "table": "read_model.oa_pending_payment_scopes",
        "tenant_scoped": False,
        "status_expr": "coalesce(nullif(cache_status, ''), 'fresh')",
        "schema_expr": "''",
        "last_error_expr": "''",
    },
    "pending_invoice": {
        "table": "read_model.pending_invoice_scopes",
        "tenant_scoped": False,
        "status_expr": "coalesce(nullif(cache_status, ''), 'fresh')",
        "schema_expr": "''",
        "last_error_expr": "''",
    },
}


APP_STATUS_READINESS_BACKFILL_ROW_TABLES = {
    "search": {
        "table": "read_model.search_index_rows",
        "status_expr": "coalesce((array_agg(coalesce(nullif(cache_status, ''), 'fresh') order by generated_at desc))[1], 'fresh')",
        "schema_expr": "''",
    },
    "cost_statistics": {
        "table": "read_model.cost_statistics_read_models",
        "status_expr": "'fresh'",
        "schema_expr": "''",
    },
    "tax_offset": {
        "table": "read_model.tax_offset_read_models",
        "status_expr": "coalesce((array_agg(coalesce(nullif(cache_status, ''), 'fresh') order by generated_at desc))[1], 'fresh')",
        "schema_expr": "coalesce((array_agg(schema_version order by generated_at desc))[1], '')",
    },
    "no_oa_bank_batch": {
        "table": "read_model.no_oa_bank_batch_rows",
        "status_expr": "coalesce((array_agg(coalesce(nullif(cache_status, ''), 'fresh') order by generated_at desc))[1], 'fresh')",
        "schema_expr": "''",
    },
    "turnover_ledger": {
        "table": "read_model.turnover_ledger_rows",
        "status_expr": "coalesce((array_agg(coalesce(nullif(cache_status, ''), 'fresh') order by generated_at desc))[1], 'fresh')",
        "schema_expr": "''",
    },
}
