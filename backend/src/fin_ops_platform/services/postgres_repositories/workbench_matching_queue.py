from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import (
    int_value,
    jsonb,
    month_start,
    run_in_transaction,
    text,
)


class PostgresWorkbenchMatchingQueueRepository:
    """Durable queue for the canonical Workbench matching domain.

    This is a business-work queue. It does not materialize page/API query state.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def mark_workbench_matching_dirty_scopes(
        self,
        *,
        tenant_id: str,
        scope_months: list[str],
        reason: str,
        source_versions: dict[str, object],
        debounce_seconds: int,
    ) -> list[str]:
        with self._connection.transaction() as transaction:
            return self.mark_workbench_matching_dirty_scopes_in_transaction(
                transaction=transaction,
                tenant_id=tenant_id,
                scope_months=scope_months,
                reason=reason,
                source_versions=source_versions,
                debounce_seconds=debounce_seconds,
            )

    @staticmethod
    def mark_workbench_matching_dirty_scopes_in_transaction(
        *,
        transaction: Any,
        tenant_id: str,
        scope_months: list[str],
        reason: str,
        source_versions: dict[str, object],
        debounce_seconds: int,
    ) -> list[str]:
        normalized_months = sorted(
            {str(month)[:7] for month in scope_months if str(month or "").strip()}
        )
        for scope_month in normalized_months:
            transaction.execute(
                """
                insert into job.workbench_matching_dirty_scopes(
                    tenant_id, scope_month, reason, status, available_at, source_versions, raw_payload
                )
                values (
                    %s, %s::date, %s, 'dirty', now() + (%s::text || ' seconds')::interval, %s, %s
                )
                on conflict (tenant_id, scope_month) do update set
                    reason = excluded.reason,
                    status = case
                        when job.workbench_matching_dirty_scopes.status = 'processing' then 'processing'
                        else 'dirty'
                    end,
                    available_at = case
                        when job.workbench_matching_dirty_scopes.status = 'processing'
                            then job.workbench_matching_dirty_scopes.available_at
                        when coalesce((excluded.raw_payload->>'expedite')::boolean, false)
                            then least(job.workbench_matching_dirty_scopes.available_at, excluded.available_at)
                        else greatest(job.workbench_matching_dirty_scopes.available_at, excluded.available_at)
                    end,
                    source_versions = job.workbench_matching_dirty_scopes.source_versions || excluded.source_versions,
                    raw_payload = coalesce(job.workbench_matching_dirty_scopes.raw_payload, '{}'::jsonb)
                        || excluded.raw_payload
                        || case
                            when job.workbench_matching_dirty_scopes.status = 'processing'
                                then '{"refresh_requested_while_processing":true}'::jsonb
                            else '{}'::jsonb
                           end,
                    lease_owner = case
                        when job.workbench_matching_dirty_scopes.status = 'processing'
                            then job.workbench_matching_dirty_scopes.lease_owner
                        else null
                    end,
                    lease_expires_at = case
                        when job.workbench_matching_dirty_scopes.status = 'processing'
                            then job.workbench_matching_dirty_scopes.lease_expires_at
                        else null
                    end,
                    updated_at = now()
                """,
                (
                    text(tenant_id) or "default",
                    month_start(scope_month),
                    text(reason),
                    max(0, int_value(debounce_seconds, 60)),
                    jsonb(source_versions),
                    jsonb(
                        {
                            "reason": reason,
                            "source_versions": source_versions,
                            "expedite": max(0, int_value(debounce_seconds, 60)) == 0,
                        }
                    ),
                ),
            )
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
                      and status in ('completed', 'failed')
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
                    raw_payload = coalesce(raw_payload, '{}'::jsonb) - 'refresh_requested_while_processing',
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

    def retry_failed_workbench_matching_scope(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        reason: str,
        expected_attempt_count: int,
        expected_request_id: str,
        expected_last_error: str,
        expected_source_versions: dict[str, object],
    ) -> bool:
        def write(connection: Any) -> bool:
            row = connection.fetch_one(
                """
                update job.workbench_matching_dirty_scopes
                set reason = %s,
                    status = 'dirty',
                    available_at = now(),
                    lease_owner = null,
                    lease_expires_at = null,
                    raw_payload = coalesce(raw_payload, '{}'::jsonb)
                        || jsonb_build_object('reason', cast(%s as text), 'expedite', true),
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = %s::date
                  and status = 'failed'
                  and attempt_count = %s
                  and coalesce(request_id, '') = %s
                  and coalesce(last_error, '') = %s
                  and coalesce(source_versions, '{}'::jsonb) = %s
                returning id
                """,
                (
                    text(reason),
                    text(reason),
                    text(tenant_id) or "default",
                    month_start(scope_month),
                    max(0, int_value(expected_attempt_count, 0)),
                    text(expected_request_id) or "",
                    text(expected_last_error) or "",
                    jsonb(expected_source_versions),
                ),
            )
            return isinstance(row, dict)

        return bool(run_in_transaction(self._connection, write))

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
                set status = case
                        when coalesce((raw_payload->>'refresh_requested_while_processing')::boolean, false)
                            then 'dirty'
                        else 'completed'
                    end,
                    available_at = case
                        when coalesce((raw_payload->>'refresh_requested_while_processing')::boolean, false)
                            then now()
                        else available_at
                    end,
                    completed_at = case
                        when coalesce((raw_payload->>'refresh_requested_while_processing')::boolean, false)
                            then null
                        else now()
                    end,
                    failed_at = null,
                    duration_ms = greatest(0, floor(extract(epoch from (now() - started_at)) * 1000)::integer),
                    source_versions = %s,
                    lease_owner = null,
                    lease_expires_at = null,
                    raw_payload = coalesce(raw_payload, '{}'::jsonb) - 'refresh_requested_while_processing',
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
                    raw_payload = coalesce(raw_payload, '{{}}'::jsonb) - 'refresh_requested_while_processing',
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


def _retry_backoff_case_sql(retry_backoff_seconds: list[int]) -> str:
    backoffs = [max(0, int_value(value, 0)) for value in retry_backoff_seconds]
    if not backoffs:
        backoffs = [0]
    clauses = " ".join(
        f"when attempt_count + 1 = {index} then {delay_seconds}"
        for index, delay_seconds in enumerate(backoffs, start=1)
    )
    return f"case {clauses} else {backoffs[-1]} end"
