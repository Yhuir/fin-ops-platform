from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection


class PostgresReadModelScopeContractRepository:
    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def list_cost_statistics_dirty_scopes(self) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select
                id::text as id,
                tenant_id,
                scope_type,
                scope_key,
                status,
                reason,
                last_error,
                updated_at
            from job.read_model_dirty_scopes
            where scope_type = 'cost_statistics'
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc, id
            """
        )

    def list_cost_statistics_outbox_events(self) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select
                id::text as id,
                tenant_id,
                event_type,
                scope_type,
                coalesce(scope_key, payload->>'scope_key') as scope_key,
                status,
                last_error,
                updated_at
            from job.outbox_events
            where (scope_type = 'cost_statistics' or event_type = 'cost_statistics.read_model.refresh')
              and status in ('pending', 'processing', 'failed', 'dead_lettered')
            order by updated_at desc, id
            """
        )

    def list_read_model_outbox_failures(self) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select
                e.id::text as id,
                e.tenant_id,
                e.event_type,
                coalesce(e.scope_type, e.payload->>'scope_type') as scope_type,
                coalesce(e.scope_key, e.payload->>'scope_key') as scope_key,
                e.status,
                e.last_error,
                e.updated_at,
                exists (
                    select 1
                    from job.outbox_events done
                    where done.tenant_id = e.tenant_id
                      and done.event_type = e.event_type
                      and coalesce(done.scope_type, done.payload->>'scope_type', '') =
                          coalesce(e.scope_type, e.payload->>'scope_type', '')
                      and coalesce(done.scope_key, done.payload->>'scope_key', '') =
                          coalesce(e.scope_key, e.payload->>'scope_key', '')
                      and done.status = 'done'
                      and done.updated_at > e.updated_at
                ) as covered_by_later_done,
                exists (
                    select 1
                    from read_model.app_status_readiness readiness
                    where readiness.tenant_id = e.tenant_id
                      and coalesce(readiness.scope_type, '') = coalesce(e.scope_type, e.payload->>'scope_type', '')
                      and coalesce(readiness.scope_key, '') = coalesce(e.scope_key, e.payload->>'scope_key', '')
                      and readiness.status = 'fresh'
                      and readiness.updated_at > e.updated_at
                ) as covered_by_later_readiness
            from job.outbox_events e
            where e.event_type like '%%.read_model.refresh'
              and e.status in ('failed', 'dead_lettered', 'publish_failed')
            order by e.updated_at desc, e.id
            """
        )

    def list_cost_statistics_readiness(self) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select
                tenant_id,
                read_model_key,
                scope_type,
                scope_key,
                status,
                last_error,
                updated_at
            from read_model.app_status_readiness
            where read_model_key = 'cost_statistics'
               or scope_type = 'cost_statistics'
            order by updated_at desc, tenant_id, read_model_key, scope_type, scope_key
            """
        )

    def delete_dirty_scope(self, row_id: str) -> int:
        return self._connection.execute(
            "delete from job.read_model_dirty_scopes where id = %s",
            (row_id,),
        )

    def delete_outbox_event(self, row_id: str) -> int:
        return self._connection.execute(
            "delete from job.outbox_events where id = %s",
            (row_id,),
        )

    def delete_readiness(self, *, tenant_id: str, read_model_key: str, scope_type: str, scope_key: str) -> int:
        return self._connection.execute(
            """
            delete from read_model.app_status_readiness
            where tenant_id = %s
              and read_model_key = %s
              and scope_type = %s
              and scope_key = %s
            """,
            (tenant_id, read_model_key, scope_type, scope_key),
        )

    def record_repair_audit(self, event: dict[str, Any]) -> str:
        row = self._connection.fetch_one(
            """
            insert into audit.events (
                event_type,
                object_type,
                object_id,
                actor_id,
                scope,
                payload,
                raw_payload
            ) values (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s::jsonb,
                %s::jsonb
            )
            returning id::text as id
            """,
            (
                str(event.get("event_type") or "read_model_scope_contract_repair"),
                str(event.get("object_type") or "read_model_runtime_repair"),
                str(event.get("object_id") or "cost_statistics"),
                "system",
                "runtime",
                json.dumps(event.get("payload") or {}, ensure_ascii=False, sort_keys=True, default=str),
                json.dumps(event, ensure_ascii=False, sort_keys=True, default=str),
            ),
        )
        return str((row or {}).get("id") or "")
