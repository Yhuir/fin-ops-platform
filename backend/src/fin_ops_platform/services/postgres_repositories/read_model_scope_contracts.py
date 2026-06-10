from __future__ import annotations

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
