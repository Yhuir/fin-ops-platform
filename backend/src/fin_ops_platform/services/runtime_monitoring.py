from __future__ import annotations

from typing import Any


class RuntimeMonitoringRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def health_summary(self, *, stale_after_seconds: int = 300) -> dict[str, Any]:
        queue_rows = self._connection.fetch_all(
            """
            select status, count(*)::bigint as count
            from job.outbox_events
            group by status
            order by status
            """
        )
        age_row = self._connection.fetch_one(
            """
            select extract(epoch from max(now() - created_at))::float as max_pending_age_seconds
            from job.outbox_events
            where status = 'pending'
            """
        )
        stale_rows = self._connection.fetch_all(
            """
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
        queue_backlog = {str(row["status"]): int(row["count"]) for row in queue_rows}
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
        return {
            "queue_backlog": queue_backlog,
            "failed_jobs": int(queue_backlog.get("failed", 0)),
            "max_pending_age_seconds": (age_row or {}).get("max_pending_age_seconds"),
            "stale_dirty_scope_count": len(stale_dirty_scopes),
            "stale_dirty_scopes": stale_dirty_scopes,
        }
