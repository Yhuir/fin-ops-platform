# Production No-OA Bank Batch Dead-Letter Read-Only Diagnosis 2026-06-25

**Boundary:** `production:no-oa-bank-batch-dead-letter-read-only-diagnosis`
**Final status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `e9d9ce0a7206e4e757cf12e38396e767b5ef2ace`

## Target Boundary

Diagnose the remaining production blocker after PostgreSQL and app/worker recovery:

- one stale `no_oa_bank_batch:all` dirty scope;
- one dead-lettered `no_oa_bank_batch.read_model.refresh` event;
- last error: FK violation between `app.no_oa_bank_batches` and `app.no_oa_bank_batch_events`.

This boundary is read-only. It must not repair, requeue, mark done, delete rows or replay workers.

## Local Contract Evidence

Repository schema and code explain the likely failure path:

- `backend/src/fin_ops_platform/postgres/migrations/0003_workbench_relations_exceptions.sql` defines `app.no_oa_bank_batch_events.no_oa_bank_batch_id uuid references app.no_oa_bank_batches(id)`.
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py::save_no_oa_bank_batches(...)` deletes `app.no_oa_bank_batches` rows whose `batch_id` is not in the new public snapshot before inserting/upserting the remaining rows.
- The same repository later replaces events by deleting/inserting `app.no_oa_bank_batch_events` for batch ids present in the snapshot audit log.
- If production contains events that reference a batch omitted from the new snapshot, the batch delete can fail with the observed FK violation.
- `backend/src/fin_ops_platform/tools/runtime_queue_ops.py` already contains dry-run eligibility logic for dead-letter resolution, but this boundary must not execute it.

## Allowed Read-Only Commands

Allowed:

- root SSH identity;
- `/health/ready` structured summary;
- read-only PostgreSQL session using local PostgreSQL peer access as `postgres`, with `set default_transaction_read_only = on`;
- schema/FK introspection for `app.no_oa_bank_batches`, `app.no_oa_bank_batch_events`, `job.outbox_events`, `job.read_model_dirty_scopes` and readiness rows;
- aggregate counts and sampled identifiers needed to identify exact scope.

Forbidden:

- print env files, DSNs, passwords, tokens, cookies, private keys or secret env values;
- `update`, `insert`, `delete`, `truncate`, `alter`, `drop`, `vacuum full`, `reindex`, `systemctl restart`, deploy, queue replay or worker replay;
- `runtime_queue_ops --execute`, repair tools with `--apply`, mark-done, requeue, readiness mutation or FK cleanup.

## Exact Read-Only Commands

```bash
ssh finops-prod-root 'set -u; printf "identity user=%s uid=%s host=%s time=%s\n" "$(whoami)" "$(id -u)" "$(hostname)" "$(date -Is)"'

ssh finops-prod-root 'set -u; python3 - <<'"'"'PY'"'"'
import json, subprocess, time
url = "http://127.0.0.1:18001/health/ready"
start = time.monotonic()
proc = subprocess.run(["curl", "-sS", "-m", "30", "-w", "\n__HTTP__:%{http_code} __TIME__:%{time_total}\n", url], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
body, _, meta = proc.stdout.partition("\n__HTTP__:")
print(f"curl_returncode={proc.returncode} elapsed={time.monotonic() - start:.3f}s")
print("__HTTP__:" + meta.strip())
payload = json.loads(body)
print("status=" + str(payload.get("status")))
infra = payload.get("runtime_infrastructure") or {}
for key in ["queue_backlog", "dirty_scopes", "failed_jobs", "stale_dirty_scope_count", "missing_required_worker_count", "stale_required_worker_count", "mismatched_required_worker_count", "worker_status_counts"]:
    print(f"{key}={infra.get(key)}")
for key in ["stale_dirty_scopes_summary", "dirty_scopes_by_scope_summary", "pending_outbox_events_by_scope_summary"]:
    value = infra.get(key)
    if value:
        print(f"{key}={json.dumps(value, ensure_ascii=False)[:1600]}")
PY'

ssh finops-prod-root 'runuser -u postgres -- psql -d fin_ops -v ON_ERROR_STOP=1 -P pager=off -P tuples_only=off <<'"'"'SQL'"'"'
set default_transaction_read_only = on;
begin read only;

select
  id::text as event_id,
  tenant_id,
  event_type,
  scope_type,
  scope_key,
  status,
  attempts,
  source_version,
  created_at,
  updated_at,
  processed_at,
  dead_lettered_at,
  left(coalesce(last_error, ''), 500) as last_error_prefix
from job.outbox_events
where event_type = 'no_oa_bank_batch.read_model.refresh'
  and scope_type = 'no_oa_bank_batch'
  and scope_key = 'all'
order by updated_at desc, created_at desc
limit 10;

select
  tenant_id,
  scope_type,
  scope_key,
  status,
  attempts,
  source_version,
  created_at,
  updated_at,
  left(coalesce(last_error, ''), 500) as last_error_prefix
from job.read_model_dirty_scopes
where scope_type = 'no_oa_bank_batch'
  and scope_key = 'all'
order by updated_at desc, created_at desc
limit 10;

select
  read_model_key,
  scope_type,
  scope_key,
  status,
  source_versions,
  updated_at
from read_model.app_status_readiness
where read_model_key = 'no_oa_bank_batch'
order by updated_at desc
limit 20;

select
  conname,
  pg_get_constraintdef(oid) as definition
from pg_constraint
where conrelid = 'app.no_oa_bank_batch_events'::regclass
order by conname;

select
  count(*) as orphan_event_count
from app.no_oa_bank_batch_events e
left join app.no_oa_bank_batches b on b.id = e.no_oa_bank_batch_id
where e.no_oa_bank_batch_id is not null
  and b.id is null;

select
  b.batch_id,
  b.id::text as batch_uuid,
  b.status,
  b.updated_at,
  count(e.id) as event_count
from app.no_oa_bank_batches b
join app.no_oa_bank_batch_events e on e.no_oa_bank_batch_id = b.id
where b.id::text = 'ee4f337e-2f71-504b-8d28-c0236668662f'
group by b.batch_id, b.id, b.status, b.updated_at;

select
  count(*) as event_count_for_failed_batch_uuid
from app.no_oa_bank_batch_events e
where e.no_oa_bank_batch_id::text = 'ee4f337e-2f71-504b-8d28-c0236668662f';

select
  b.batch_id,
  b.id::text as batch_uuid,
  b.status,
  b.status_bucket,
  b.scope_month,
  b.updated_at,
  coalesce(jsonb_array_length(case when jsonb_typeof(b.raw_payload -> 'bank_transaction_ids') = 'array' then b.raw_payload -> 'bank_transaction_ids' else '[]'::jsonb end), 0) as raw_bank_txn_count
from app.no_oa_bank_batches b
where b.id::text = 'ee4f337e-2f71-504b-8d28-c0236668662f'
   or b.batch_id = 'ee4f337e-2f71-504b-8d28-c0236668662f'
limit 20;

rollback;
SQL'
```

## Stop Gates

Stop the boundary as `production-evidence-deferred` if:

- root SSH or local PostgreSQL peer access fails;
- read-only transaction cannot be enforced;
- required table/constraint facts cannot be read without secrets;
- diagnosis shows a required next step would be DB mutation, queue mutation, worker replay or repair.

Classify as `needs-human-production-gate` only if no safe read-only diagnosis is possible or if evidence shows a production integrity issue whose scope cannot be bounded.

## Evidence Results

Executed at approximately `2026-06-25T01:42+08:00` through `ssh finops-prod-root`.

### Health Summary

```text
identity user=root uid=0 host=VM-0-6-opencloudos time=2026-06-25T01:42:26+08:00
/health/ready HTTP=200 TIME=0.513975 status=ready
queue_backlog={'dead_lettered': 1}
dirty_scopes={'done': 187006, 'pending': 1}
failed_jobs=1
stale_dirty_scope_count=1
missing_required_worker_count=0
stale_required_worker_count=0
mismatched_required_worker_count=0
worker_status_counts={'available': 21}
```

Remaining blocker was still:

```text
no_oa_bank_batch:all dirty scope status=pending attempts=0
no_oa_bank_batch.read_model.refresh scope_key=all status=dead_lettered attempts=5
```

### Queue And Readiness Evidence

The first read-only SQL attempt used an incorrect readiness column name and failed after read-only selects; no writes were executed. The corrected read-only SQL used `runuser -u postgres -- psql`, `set default_transaction_read_only = on`, `begin read only` and `rollback`.

Latest no-OA refresh evidence:

```text
event_id=3bc506fd-5662-4902-a9b9-19b0d8fbe4a6
status=dead_lettered
attempts=5
source_version=35430
created_at=2026-06-23 20:34:54.600881+08
dead_lettered_at=2026-06-23 20:50:07.430229+08
last_error=update or delete on table "no_oa_bank_batches" violates foreign key constraint "no_oa_bank_batch_events_no_oa_bank_batch_id_fkey" on table "no_oa_bank_batch_events"
```

Dirty scope evidence:

```text
tenant_id=default
scope_type=no_oa_bank_batch
scope_key=all
status=pending
attempts=0
source_version=35430
created_at=2026-06-23 16:27:32.464188+08
updated_at=2026-06-23 20:34:54.600881+08
```

Readiness evidence:

```text
read_model_key=no_oa_bank_batch
scope_type=no_oa_bank_batch
scope_key=all
status=failed
source_versions={"source_version": 35430}
updated_at=2026-06-23 20:50:07.426484+08
```

### FK And Data Shape Evidence

Constraint:

```text
no_oa_bank_batch_events_no_oa_bank_batch_id_fkey:
FOREIGN KEY (no_oa_bank_batch_id) REFERENCES app.no_oa_bank_batches(id)
```

Aggregate counts:

```text
orphan_event_count=0
dead_letter_count=14
min_source_version=35410
max_source_version=35430
first_created_at=2026-06-23 16:27:32.464188+08
last_dead_lettered_at=2026-06-23 20:50:07.430229+08
```

The failed referenced batch still exists and is not an orphan:

```text
batch_id=no_oa_batch_1efd5168a8418795686f
batch_uuid=ee4f337e-2f71-504b-8d28-c0236668662f
status=superseded
status_bucket=superseded
scope_month=2026-03-01
event_count=6
raw_bank_txn_count=0
updated_at=2026-06-23 16:03:46.084981+08
```

### Diagnosis

The production blocker is a deterministic repository write-order bug:

- no-OA public snapshot no longer includes the superseded batch;
- `save_no_oa_bank_batches(...)` tries to delete absent `app.no_oa_bank_batches` rows before deleting event rows that reference those removed batch UUIDs;
- PostgreSQL correctly blocks the delete because `app.no_oa_bank_batch_events.no_oa_bank_batch_id` references the superseded batch;
- the worker dead-letters repeated all-scope refresh events, leaving `no_oa_bank_batch:all` dirty and readiness failed.

No production DB writes, requeues, readiness mutation, worker replay, repair command, deploy, service restart or secret reads were performed in this boundary.

## Result Classification

`production-evidence-deferred`.

Reason:

- Read-only evidence proved the exact production failure shape and local contract cause.
- Full production closure remains deferred until the repository write-order fix is deployed and a controlled production convergence/requeue/verification boundary proves `no_oa_bank_batch:all` fresh.

## Next Safe Boundary

```text
read-models:no-oa-bank-batch-event-fk-delete-order-fix
```

Purpose:

- Fix `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` so event rows for removed no-OA batches are deleted before the removed batches.
- Add a regression guard for retained and empty snapshot replacement order.
- Do not change API shape, no-OA business status semantics, relation commands, worker event contract, queue schema, readiness semantics or frontend behavior.
