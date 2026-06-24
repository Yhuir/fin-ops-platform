# Production Workbench Read Model High-Row Query Plan Read-Only Runbook

**Boundary:** `production:workbench-read-model-high-row-query-plan-read-only-runbook`
**Status:** `production-controlled`
**Date:** 2026-06-25
**Branch:** `dev`
**Controller:** T0
**Closure:** module/global closure not claimed

## Objective

Collect bounded PostgreSQL-native production evidence for the Workbench high-row read-model surface after Row255 found `workbench_read_models` timing out inside shadow-read rehearsal.

This runbook does not perform API smoke, browser smoke, mutation, repair, replay or final closure.

## Safety Properties

- Uses `/health/ready` pre/post checks.
- Uses `runuser -u postgres -- psql -d fin_ops`.
- Sets `default_transaction_read_only = on`.
- Uses `begin read only` and `rollback`.
- Sets a short `statement_timeout`.
- Collects only aggregate counts, index metadata, index usage counters and `EXPLAIN` plans.
- Does not select `payload`, `raw_payload`, `column_values`, `searchable_text`, `project_name`, `counterparty_name`, invoice identifiers, row detail values, secrets, env values, DSNs, tokens or cookies.
- Does not execute `EXPLAIN ANALYZE` for broad high-row queries.
- Performs no DB writes, queue/readiness mutation, deploy, restart, requeue, repair, replay, worker consume or `--apply`.

## Commands

### 1. Precheck Health

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

### 2. Read-Only Workbench High-Row Evidence

```bash
ssh finops-prod-root 'runuser -u postgres -- psql -d fin_ops -v ON_ERROR_STOP=1 -P pager=off <<'"'"'SQL'"'"'
set default_transaction_read_only = on;
set statement_timeout = '"'"'8s'"'"';
begin read only;

select status, count(*)::bigint as generation_count, sum(row_count)::bigint as metadata_rows, sum(group_count)::bigint as metadata_groups, max(row_count)::bigint as max_metadata_rows
from read_model.workbench_generations
group by status
order by status;

select scope_key, generation_id, row_count, group_count, summary_count, activated_at
from read_model.workbench_generations
where status = '"'"'active'"'"'
order by row_count desc, group_count desc
limit 10;

select '"'"'workbench_rows'"'"' as table_name, count(*)::bigint as row_count from read_model.workbench_rows
union all
select '"'"'workbench_groups'"'"', count(*)::bigint from read_model.workbench_groups
union all
select '"'"'workbench_group_rows'"'"', count(*)::bigint from read_model.workbench_group_rows
union all
select '"'"'workbench_summary'"'"', count(*)::bigint from read_model.workbench_summary
union all
select '"'"'workbench_snapshots'"'"', count(*)::bigint from read_model.workbench_snapshots;

with active as (
    select generation_id, scope_key
    from read_model.workbench_generations
    where status = '"'"'active'"'"'
    order by row_count desc, group_count desc
    limit 5
)
select 'workbench_rows' as table_name, r.scope_key, count(*)::bigint as row_count
from read_model.workbench_rows r
join active a on a.generation_id = r.generation_id and a.scope_key = r.scope_key
group by r.scope_key
union all
select 'workbench_group_rows', gr.scope_key, count(*)::bigint
from read_model.workbench_group_rows gr
join active a on a.generation_id = gr.generation_id and a.scope_key = gr.scope_key
group by gr.scope_key
order by table_name, row_count desc;

select tablename, indexname
from pg_indexes
where schemaname = '"'"'read_model'"'"'
  and tablename in ('"'"'workbench_generations'"'"', '"'"'workbench_rows'"'"', '"'"'workbench_groups'"'"', '"'"'workbench_group_rows'"'"', '"'"'workbench_summary'"'"', '"'"'workbench_snapshots'"'"')
order by tablename, indexname;

select relname, indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
from pg_stat_user_indexes
where schemaname = '"'"'read_model'"'"'
  and relname in ('"'"'workbench_generations'"'"', '"'"'workbench_rows'"'"', '"'"'workbench_groups'"'"', '"'"'workbench_group_rows'"'"', '"'"'workbench_summary'"'"', '"'"'workbench_snapshots'"'"')
order by relname, indexrelname;

explain (format text)
with active as (
    select generation_id, scope_key
    from read_model.workbench_generations
    where status = '"'"'active'"'"'
    order by row_count desc, group_count desc
    limit 1
)
select r.row_id, r.status, r.source_kind, r.scope_key
from read_model.workbench_rows r
join active a on a.generation_id = r.generation_id and a.scope_key = r.scope_key
where r.status = '"'"'open'"'"'
order by r.updated_at desc
limit 100;

explain (format text)
with active as (
    select generation_id, scope_key
    from read_model.workbench_generations
    where status = '"'"'active'"'"'
    order by row_count desc, group_count desc
    limit 1
)
select zone, group_id, pane, row_role, row_id
from read_model.workbench_group_rows gr
join active a on a.generation_id = gr.generation_id and a.scope_key = gr.scope_key
where gr.zone = '"'"'open'"'"'
  and gr.pane = '"'"'bank'"'"'
order by gr.group_id, gr.row_index
limit 100;

rollback;
SQL'
```

### 3. Postcheck Health

```bash
ssh finops-prod-root 'set -eu; curl -fsS --max-time 8 http://127.0.0.1:18001/health/ready | /opt/fin-ops/venv/bin/python -c "import json,sys; p=json.load(sys.stdin); print({k:p.get(k) for k in (\"status\",\"release\") if k in p})"'
```

## Stop Gates

- `/health/ready` is not ready before the SQL evidence run.
- Any SQL would select payload/raw row detail/business-sensitive columns.
- Any SQL would mutate data, queues, readiness, workers or service state.
- Any command would print secrets, env values, DSNs, tokens or cookies.
- The read-only transaction or statement timeout cannot be enforced.

## Expected Evidence

- `/health/ready` ready before and after.
- Active generation aggregate counts.
- Top active scope counts by metadata and actual row tables.
- Workbench table aggregate counts.
- Workbench index names and scan counters.
- Representative EXPLAIN plans for bounded high-row page-like queries.
- Timeout or error classification if any query cannot finish under the timeout.

## Result

Completed as `production-controlled`.

### Precheck

`/health/ready` returned:

```text
{'status': 'ready'}
```

### Aggregate Evidence

Generation status:

| Status | Generation count | Metadata rows | Metadata groups | Max metadata rows |
| --- | ---: | ---: | ---: | ---: |
| `active` | 13 | 3491 | 1924 | 1624 |
| `superseded` | 634 | 651420 | 374615 | 1624 |

Top active scopes by metadata row count:

| Scope | Row count | Group count | Summary count |
| --- | ---: | ---: | ---: |
| `all` | 1624 | 925 | 1 |
| `2026-04` | 425 | 203 | 1 |
| `2026-05` | 386 | 239 | 1 |
| `2026-03` | 270 | 142 | 1 |
| `2026-06` | 237 | 174 | 1 |
| `2026-01` | 232 | 96 | 1 |
| `2026-02` | 193 | 130 | 1 |
| `2025-12` | 68 | 10 | 1 |
| `2025-11` | 35 | 3 | 1 |
| `2025-09` | 18 | 1 | 1 |

Physical table counts:

| Table | Row count |
| --- | ---: |
| `read_model.workbench_snapshots` | 647 |
| `read_model.workbench_summary` | 647 |
| `read_model.workbench_groups` | 376539 |
| `read_model.workbench_rows` | 654911 |
| `read_model.workbench_group_rows` | 729629 |

Top active scope actual row counts:

| Table | Scope | Row count |
| --- | --- | ---: |
| `workbench_group_rows` | `all` | 1804 |
| `workbench_group_rows` | `2026-04` | 503 |
| `workbench_group_rows` | `2026-05` | 417 |
| `workbench_group_rows` | `2026-03` | 297 |
| `workbench_group_rows` | `2026-06` | 237 |
| `workbench_rows` | `all` | 1624 |
| `workbench_rows` | `2026-04` | 425 |
| `workbench_rows` | `2026-05` | 386 |
| `workbench_rows` | `2026-03` | 270 |
| `workbench_rows` | `2026-06` | 237 |

Interpretation:

- Current active generation data is bounded and much smaller than the historical physical table totals.
- Historical/superseded rows dominate physical table size.
- Row255 `workbench_read_models` timeout is consistent with broad load-all/read-model snapshot behavior, not necessarily current active-generation page-query behavior.

### Index Evidence

The query returned 43 Workbench-related indexes across:

- `workbench_generations`
- `workbench_rows`
- `workbench_groups`
- `workbench_group_rows`
- `workbench_summary`
- `workbench_snapshots`

Notable active-query indexes present:

- `workbench_generations_active_scope_uidx`
- `workbench_generations_scope_status_idx`
- `workbench_rows_generation_scope_status_idx`
- `workbench_rows_generation_scope_row_uidx`
- `workbench_group_rows_generation_scope_zone_group_idx`
- `workbench_group_rows_generation_scope_zone_group_pane_role_row_...`
- `workbench_groups_generation_scope_zone_sort_idx`

Index scan counters show active use of generation/scope indexes, including:

- `workbench_generations_active_scope_uidx`: `idx_scan=3020`
- `workbench_generations_scope_status_idx`: `idx_scan=4530`
- `workbench_rows_generation_scope_row_uidx`: `idx_scan=1510`
- `workbench_rows_generation_scope_status_idx`: `idx_scan=100`
- `workbench_group_rows_generation_scope_zone_group_idx`: `idx_scan=1610`
- `workbench_group_rows_generation_scope_zone_group_pane_role_row_...`: `idx_scan=4530`
- `workbench_groups_generation_scope_zone_sort_idx`: `idx_scan=3120`

### EXPLAIN Evidence

The first combined SQL attempt collected aggregate/index evidence but the first EXPLAIN query failed because the runbook selected ambiguous `scope_key`. This was a runbook query bug, not a production runtime failure. The transaction exited without writes. The runbook was corrected to select `r.scope_key`.

The corrected EXPLAIN run completed inside the 8 second timeout.

Representative active Workbench rows query:

- Uses `workbench_generations_active_scope_uidx` to find the top active generation.
- Uses `workbench_rows_generation_scope_status_idx` through a bitmap index scan for `(generation_id, scope_key, status)`.
- Estimated rows after active generation + status filter: 46.
- Sorts the bounded result by `updated_at desc` for `limit 100`.

Representative active Workbench group rows query:

- Uses `workbench_generations_active_scope_uidx` to find the top active generation.
- Uses `workbench_group_rows_generation_scope_zone_group_idx` for `(generation_id, scope_key, zone, pane)`.
- Estimated rows after active generation + zone/pane filter: 23.
- Sorts bounded result by `group_id, row_index` for `limit 100`.

### Postcheck

`/health/ready` returned:

```text
{'status': 'ready'}
```

## Closure Impact

- This run provides PostgreSQL-native high-row evidence for Workbench active-generation query paths.
- It explains Row255's timeout as a broad load-all/snapshot-style evidence gap rather than proof that active page-like Workbench queries are unindexed.
- It does not prove authenticated API response shape, browser hydration/data behavior, export/detail flows, operation-barrier behavior, or final Workbench/module closure.
- No payload rows, business row details, secrets, env values, DSNs, DB writes, queue/readiness mutations, deploys, restarts, requeues, repairs, replays or `--apply` occurred.

## Next Boundary

`planning:post-workbench-high-row-query-plan-next-boundary-selection`
