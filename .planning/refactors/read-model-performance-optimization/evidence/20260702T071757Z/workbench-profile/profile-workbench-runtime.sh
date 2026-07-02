#!/usr/bin/env bash
set -Eeuo pipefail

src="$(systemctl show fin-ops.service -P WorkingDirectory)"
printf 'RUN_META src=%s\n' "$src"

COMMON_ENV="${FINOPS_ENV_DIR:-/etc/fin-ops}/fin-ops.common.env"
SECRETS_ENV="${FINOPS_ENV_DIR:-/etc/fin-ops}/fin-ops.secrets.env"
API_PYTHON="${FINOPS_API_PYTHON:-/opt/fin-ops/venv/bin/python}"

set -a
source "$COMMON_ENV"
source "$SECRETS_ENV"
set +a

export PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"

cd "$src"
"$API_PYTHON" - <<'PY'
from __future__ import annotations

import json
import time
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


conn = PostgresConnection(PostgresSettings.from_env())
conn.set_statement_timeout_ms(5000)


def emit(name: str, sql: str, params: tuple[Any, ...] = ()) -> None:
    started = time.perf_counter()
    try:
        rows = conn.fetch_all(sql, params)
        payload = {
            "name": name,
            "status": "ok",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "rows": rows,
        }
    except Exception as exc:
        payload = {
            "name": name,
            "status": "error",
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": str(exc)[:800],
        }
    print("SECTION " + json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str), flush=True)


emit(
    "recent_workbench_refresh_events",
    """
    select
      id::text as event_id,
      scope_key,
      status,
      created_at::text as created_at,
      processed_at::text as processed_at,
      updated_at::text as updated_at,
      round((extract(epoch from (processed_at - created_at)) * 1000)::numeric, 3)::float
        as enqueue_to_processed_ms,
      nullif(raw_payload->'runtime_result'->>'duration_ms', '')::float as handler_duration_ms,
      raw_payload->>'reason' as reason,
      raw_payload->'runtime_result' as runtime_result
    from job.outbox_events
    where event_type = 'workbench.read_model.refresh'
    order by updated_at desc
    limit 20
    """,
)

emit(
    "active_workbench_generations",
    """
    select
      generation_id,
      scope_key,
      row_count,
      group_count,
      generated_at::text as generated_at,
      activated_at::text as activated_at,
      updated_at::text as updated_at
    from read_model.workbench_generations
    where tenant_id = 'default'
      and status = 'active'
    order by scope_key
    """,
)

emit(
    "active_workbench_detail_counts",
    """
    with active as (
      select generation_id, scope_key
      from read_model.workbench_generations
      where tenant_id = 'default'
        and status = 'active'
    )
    select
      a.scope_key,
      a.generation_id,
      (
        select count(*)::bigint
        from read_model.workbench_rows wr
        where wr.generation_id = a.generation_id
      ) as workbench_rows,
      (
        select count(*)::bigint
        from read_model.workbench_groups wg
        where wg.generation_id = a.generation_id
      ) as workbench_groups,
      (
        select count(*)::bigint
        from read_model.workbench_group_rows wgr
        where wgr.generation_id = a.generation_id
      ) as workbench_group_rows
    from active a
    order by a.scope_key
    """,
)

emit(
    "workbench_generation_retention_profile",
    """
    select
      scope_key,
      status,
      count(*)::bigint as generation_count,
      min(updated_at)::text as oldest_updated_at,
      max(updated_at)::text as newest_updated_at
    from read_model.workbench_generations
    where tenant_id = 'default'
    group by scope_key, status
    order by generation_count desc, scope_key, status
    limit 40
    """,
)

emit(
    "workbench_table_size_profile",
    """
    select
      schemaname,
      relname,
      n_live_tup,
      n_dead_tup,
      pg_relation_size(relid) as heap_bytes,
      pg_indexes_size(relid) as index_bytes,
      pg_total_relation_size(relid) as total_bytes,
      last_vacuum::text as last_vacuum,
      last_autovacuum::text as last_autovacuum,
      last_analyze::text as last_analyze,
      last_autoanalyze::text as last_autoanalyze
    from pg_stat_user_tables
    where schemaname = 'read_model'
      and relname in (
        'workbench_generations',
        'workbench_snapshots',
        'workbench_summary',
        'workbench_rows',
        'workbench_groups',
        'workbench_group_rows'
      )
    order by total_bytes desc
    """,
)

emit(
    "pg_stat_workbench_queries",
    """
    select
      calls,
      round(total_exec_time::numeric, 3)::float as total_exec_time_ms,
      round(mean_exec_time::numeric, 3)::float as mean_exec_time_ms,
      rows,
      left(regexp_replace(query, '\\s+', ' ', 'g'), 600) as query
    from pg_stat_statements
    where query ilike any(array[
      '%insert into read_model.workbench_rows%',
      '%insert into read_model.workbench_groups%',
      '%insert into read_model.workbench_group_rows%',
      '%insert into read_model.workbench_snapshots%',
      '%insert into read_model.workbench_summary%',
      '%read_model.workbench_generations%',
      '%app.bank_transactions%',
      '%app.invoices%',
      '%app.oa_applications%'
    ])
    order by total_exec_time desc
    limit 20
    """,
)
PY
