# Runtime SQL Read Model Convergence Module 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared PostgreSQL durable queue, dirty scope, worker runtime, Redis helper, object storage interface, and observability foundation without changing business read/write behavior.

**Architecture:** Module 1 only creates reusable infrastructure. PostgreSQL remains the durable source for jobs, outbox, dirty scopes, and recovery; Redis is optional and only accelerates cache/wakeup behavior; object storage is introduced as an interface/config boundary but no business file path is cut over yet.

**Tech Stack:** Python stdlib, PostgreSQL SQL migrations in `backend/src/fin_ops_platform/postgres/migrations/`, psycopg-backed `PostgresConnection`, existing `unittest` suite, optional Redis client loaded lazily, S3-compatible object storage interface implemented without adding a required runtime dependency in this module.

---

## Scope Boundary

This plan implements Module 1 from `docs/superpowers/specs/2026-05-21-runtime-sql-read-model-convergence-design.md`.

In scope:

- Add schema migration `0009_runtime_infrastructure.sql`.
- Add durable queue and dirty scope repositories.
- Add worker runtime loop and CLI entrypoint.
- Add Redis helper with graceful unavailable behavior.
- Add object storage interface and configuration validation.
- Add health summary helpers for queue backlog, dirty scopes, Redis, and object storage config.
- Add focused tests and docs.

Out of scope:

- Do not cut over workbench, imports, cost statistics, tax offset, search, OA, or file upload paths.
- Do not modify `Application.__init__` snapshot loading yet. That is Module 2.
- Do not add boto3/minio/redis as required dependencies unless an existing dependency already provides the capability. Module 1 may use lazy imports and typed protocols.
- Do not remove old Mongo/GridFS/JSON snapshot paths.

## File Structure

- Create `backend/src/fin_ops_platform/postgres/migrations/0009_runtime_infrastructure.sql`
  - Adds/extends durable queue, dirty scope, and object-storage support schema.
- Create `backend/src/fin_ops_platform/services/runtime_queue.py`
  - Defines queue dataclasses, repository, claim/complete/fail/retry/dedupe logic.
- Create `backend/src/fin_ops_platform/services/read_model_dirty_scope_repository.py`
  - Defines dirty scope dataclasses and repository.
- Create `backend/src/fin_ops_platform/services/runtime_worker.py`
  - Provides worker registry, polling loop, one-shot processing, and health summary.
- Create `backend/src/fin_ops_platform/tools/run_runtime_worker.py`
  - CLI entrypoint for independent worker process.
- Create `backend/src/fin_ops_platform/services/redis_runtime.py`
  - Optional Redis helper for short TTL cache, pub/sub wakeup, and health state.
- Create `backend/src/fin_ops_platform/services/object_storage.py`
  - Object storage protocol, settings, unsupported/not-configured implementation, and in-memory test implementation.
- Modify `backend/src/fin_ops_platform/app/main.py`
  - Add no behavior-changing import-free help text only if needed; prefer new tool entrypoint instead.
- Do not modify historical migration `backend/src/fin_ops_platform/postgres/migrations/0007_grants.sql`
  - New table grants must be included inside `0009_runtime_infrastructure.sql`, because deployed databases may already have applied `0007`.
- Modify `tests/test_postgres_migrations.py`
  - Add `0009_runtime_infrastructure.sql` and expected tables/index text.
- Modify `tests/postgres_test_utils.py`
  - Add new tables to integration truncate lists if integration helpers need them.
- Create `tests/test_runtime_queue.py`
  - Unit tests for queue repository SQL shape plus skip-safe PostgreSQL integration tests when `FIN_OPS_TEST_DATABASE_URL` is configured.
- Create `tests/test_runtime_worker.py`
  - Unit tests for worker dispatch, retry, missing handlers, and one-shot mode.
- Create `tests/test_runtime_infrastructure_helpers.py`
  - Unit tests for Redis helper and object storage settings.
- Create `tests/test_runtime_infrastructure_postgres_integration.py`
  - Skip-safe PostgreSQL integration tests for migration 0009, queue behavior, and dirty scope stale-complete behavior.
- Modify `backend/README.md`
  - Add worker startup and infrastructure configuration notes.
- Modify `docs/dev/backend.md`
  - Document Module 1 infrastructure boundaries.
- Modify `docs/operations/deployment.md` if present
  - Add Redis/MinIO/worker environment variables without requiring cutover.

## Acceptance Criteria

- `python3 -m unittest tests.test_postgres_migrations tests.test_runtime_queue tests.test_read_model_dirty_scope_repository tests.test_runtime_worker tests.test_runtime_infrastructure_helpers -v` passes.
- `python3 -m unittest tests.test_runtime_infrastructure_postgres_integration -v` skips safely without `FIN_OPS_TEST_DATABASE_URL` and passes against a disposable PostgreSQL test database.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres plan --migrations-dir backend/src/fin_ops_platform/postgres/migrations` lists `0009 pending runtime_infrastructure` without requiring a database URL.
- Worker can run in one-shot mode with no pending work and exit successfully.
- Runtime infrastructure health CLI prints JSON without exposing secrets.
- Queue repository supports enqueue, dedupe, claim with lock timeout, complete, fail with retry, and fail permanent.
- Dirty scope repository supports mark dirty, coalescing by `(tenant_id, scope_type, scope_key)`, claim, complete, fail, and supersede behavior.
- Redis helper reports unavailable cleanly when Redis package/config is absent; no correctness path depends on Redis.
- Object storage settings validate required S3-compatible config, but no business file upload uses object storage yet.
- No business API behavior changes.

---

## Task 1: Add Runtime Infrastructure Migration

**Files:**
- Create: `backend/src/fin_ops_platform/postgres/migrations/0009_runtime_infrastructure.sql`
- Modify: `tests/test_postgres_migrations.py`
- Modify: `tests/postgres_test_utils.py`

- [ ] **Step 1: Write failing migration discovery test**

Update `EXPECTED_MIGRATIONS` and `EXPECTED_MIGRATION_FILES` to include:

```python
"0009_runtime_infrastructure.sql",
```

Update the existing migration version assertion from:

```python
[f"{number:04d}" for number in range(1, 9)]
```

to:

```python
[f"{number:04d}" for number in range(1, 10)]
```

Add these expected tables:

```python
"job.read_model_dirty_scopes",
"job.runtime_worker_heartbeats",
```

Add required SQL text assertions for:

```python
"outbox_events_dedupe_uidx"
"read_model_dirty_scopes_active_uidx"
"runtime_worker_heartbeats_worker_uidx"
"grant select, insert, update on job.read_model_dirty_scopes to fin_ops_worker"
"grant select, insert, update on job.runtime_worker_heartbeats to fin_ops_worker"
```

Add an offline plan assertion that output includes:

```text
0009 pending runtime_infrastructure
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
```

Expected: fail because `0009_runtime_infrastructure.sql` does not exist.

- [ ] **Step 3: Add migration**

Create `0009_runtime_infrastructure.sql` with:

```sql
alter table job.outbox_events
    add column if not exists tenant_id text not null default 'default',
    add column if not exists scope_type text,
    add column if not exists scope_key text,
    add column if not exists dedupe_key text,
    add column if not exists attempts integer not null default 0,
    add column if not exists processed_at timestamptz;

update job.outbox_events
set attempts = greatest(attempts, attempt_count)
where attempts = 0 and attempt_count > 0;

create unique index if not exists outbox_events_dedupe_uidx
    on job.outbox_events (tenant_id, dedupe_key)
    where dedupe_key is not null and status in ('pending', 'processing');

create index if not exists outbox_events_claim_idx
    on job.outbox_events (status, available_at, locked_at);

create table if not exists job.read_model_dirty_scopes (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    scope_type text not null,
    scope_key text not null,
    month date,
    reason text,
    source_version bigint not null default 0,
    status text not null default 'pending',
    attempts integer not null default 0,
    locked_by text,
    locked_at timestamptz,
    next_run_at timestamptz not null default now(),
    last_error text,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (status in ('pending', 'processing', 'done', 'failed', 'superseded'))
);

create unique index if not exists read_model_dirty_scopes_active_uidx
    on job.read_model_dirty_scopes (tenant_id, scope_type, scope_key)
    where status in ('pending', 'processing');

create index if not exists read_model_dirty_scopes_claim_idx
    on job.read_model_dirty_scopes (status, next_run_at, locked_at);

create index if not exists read_model_dirty_scopes_scope_idx
    on job.read_model_dirty_scopes (tenant_id, scope_type, scope_key, updated_at desc);

create table if not exists job.runtime_worker_heartbeats (
    id uuid primary key default gen_random_uuid(),
    worker_id text not null,
    worker_kind text not null,
    status text not null,
    last_seen_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists runtime_worker_heartbeats_worker_uidx
    on job.runtime_worker_heartbeats (worker_id);

alter table app.file_objects
    add column if not exists etag text,
    add column if not exists migration_status text;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant usage on schema job to fin_ops_api;
        grant select, insert, update on job.outbox_events to fin_ops_api;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_api;
        grant usage, select on all sequences in schema job to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant usage on schema job to fin_ops_worker;
        grant select, insert, update on job.outbox_events to fin_ops_worker;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_worker;
        grant select, insert, update on job.runtime_worker_heartbeats to fin_ops_worker;
        grant usage, select on all sequences in schema job to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant usage on schema job to fin_ops_readonly;
        grant select on job.outbox_events to fin_ops_readonly;
        grant select on job.read_model_dirty_scopes to fin_ops_readonly;
        grant select on job.runtime_worker_heartbeats to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant usage, create on schema job to fin_ops_migrator;
        grant select, insert, update on job.outbox_events to fin_ops_migrator;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_migrator;
        grant select, insert, update on job.runtime_worker_heartbeats to fin_ops_migrator;
        grant usage, select on all sequences in schema job to fin_ops_migrator;
    end if;
end $$;
```

Use existing `app.file_objects.legacy_gridfs_id` for GridFS source identity. Do not add `source_gridfs_id` unless a later migration defines a distinct meaning.

- [ ] **Step 4: Run migration tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
```

Expected: pass.

- [ ] **Step 5: Add skip-safe PostgreSQL migration integration test**

Create `tests/test_runtime_infrastructure_postgres_integration.py` with a test that:

- Uses `require_postgres_test_database_url()`.
- Runs `apply_test_migrations(database_url)`.
- Verifies `job.read_model_dirty_scopes` and `job.runtime_worker_heartbeats` exist.
- Verifies new columns on `job.outbox_events` exist.

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_postgres_integration -v
```

Expected: skip without `FIN_OPS_TEST_DATABASE_URL`, pass with a disposable PostgreSQL test database.

- [ ] **Step 6: Commit migration**

```bash
git add backend/src/fin_ops_platform/postgres/migrations/0009_runtime_infrastructure.sql tests/test_postgres_migrations.py tests/postgres_test_utils.py tests/test_runtime_infrastructure_postgres_integration.py
git commit -m "feat: add runtime infrastructure schema"
```

## Task 2: Implement Durable Queue Repository

**Files:**
- Create: `backend/src/fin_ops_platform/services/runtime_queue.py`
- Create: `tests/test_runtime_queue.py`

- [ ] **Step 1: Write tests for enqueue and dedupe**

Create unit tests using a fake transaction object that records SQL and returns controlled rows. Cover:

- `enqueue()` inserts `tenant_id`, `event_type`, `aggregate_type`, `aggregate_id`, `scope_type`, `scope_key`, `dedupe_key`, `payload`, `available_at`.
- `enqueue()` returns existing active event when dedupe key conflicts.
- `claim_next()` uses row lock semantics and lock timeout.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue -v
```

Expected: fail because module does not exist.

- [ ] **Step 3: Implement queue dataclasses and repository**

Add:

```python
@dataclass(frozen=True)
class RuntimeQueueEvent:
    event_id: str
    tenant_id: str
    event_type: str
    aggregate_type: str | None
    aggregate_id: str | None
    scope_type: str | None
    scope_key: str | None
    dedupe_key: str | None
    payload: dict[str, Any]
    attempts: int
    status: str
```

Repository methods:

- `enqueue(...) -> RuntimeQueueEvent`
- `claim_next(worker_id, event_types=None, lock_timeout_seconds=300) -> RuntimeQueueEvent | None`
- `complete(event_id, worker_id, result_payload=None) -> bool`
- `fail(event_id, worker_id, error, retry=True, retry_delay_seconds=60) -> bool`
- `backlog_summary() -> dict[str, object]`

Use `PostgresConnection.transaction()` and `for update skip locked`.

- [ ] **Step 4: Run queue tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue -v
```

Expected: pass.

- [ ] **Step 5: Add skip-safe PostgreSQL queue integration tests**

Extend `tests/test_runtime_infrastructure_postgres_integration.py` to cover real PostgreSQL behavior:

- `enqueue()` inserts a pending event.
- duplicate active `dedupe_key` returns/coalesces the same active event.
- `claim_next()` changes status to `processing` and sets lock fields.
- `complete()` marks the event `done` and sets `processed_at`.
- `fail(..., retry=True)` increments attempts and schedules `pending`.
- `fail(..., retry=False)` marks `failed`.

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_postgres_integration -v
```

Expected: skip without `FIN_OPS_TEST_DATABASE_URL`, pass with a disposable PostgreSQL test database.

- [ ] **Step 6: Commit queue repository**

```bash
git add backend/src/fin_ops_platform/services/runtime_queue.py tests/test_runtime_queue.py tests/test_runtime_infrastructure_postgres_integration.py
git commit -m "feat: add durable runtime queue repository"
```

## Task 3: Implement Dirty Scope Repository

**Files:**
- Create: `backend/src/fin_ops_platform/services/read_model_dirty_scope_repository.py`
- Modify: `tests/test_runtime_queue.py` or create `tests/test_read_model_dirty_scope_repository.py`

- [ ] **Step 1: Write dirty scope tests**

Cover:

- Marking a dirty scope creates or updates one active row.
- Newer `source_version` supersedes older pending or processing work.
- Claim sets `processing`, `locked_by`, and `locked_at`.
- Complete only succeeds for matching worker lock.
- Stale complete rejects an older `source_version` and requeues or leaves pending work for the newer version.
- Fail increments attempts and schedules retry.

Required state rules:

- Active statuses are `pending` and `processing`; the partial unique key is `(tenant_id, scope_type, scope_key)` over active statuses.
- `mark_dirty` coalesces into the active row when one exists.
- `mark_dirty` sets `source_version = greatest(existing.source_version, incoming.source_version)`.
- If `mark_dirty` receives a newer version while a row is `processing`, it clears `locked_by`/`locked_at`, sets status back to `pending`, and schedules `next_run_at = now()` so a worker rebuilds the newest scope.
- If `mark_dirty` receives an equal or older version while `processing`, it keeps the processing lock but can merge `reason`/`payload`.
- `complete(scope_id, worker_id, source_version)` succeeds only when `status = 'processing'`, lock matches `worker_id`, and stored `source_version <= completed source_version`.
- If `complete` sees stored `source_version > completed source_version`, it must not mark `done`; it should set status to `pending`, clear the stale lock, and return `False`.
- `fail(scope_id, worker_id, error)` only mutates rows locked by the worker; retry keeps the same active row pending.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_dirty_scope_repository -v
```

Expected: fail because module does not exist.

- [ ] **Step 3: Implement repository**

Methods:

- `mark_dirty(tenant_id, scope_type, scope_key, month=None, reason=None, source_version=0, payload=None)`
- `claim_next(worker_id, scope_types=None, lock_timeout_seconds=300)`
- `complete(scope_id, worker_id, source_version)`
- `fail(scope_id, worker_id, error, retry_delay_seconds=60)`
- `summary()`

- [ ] **Step 4: Run dirty scope tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_dirty_scope_repository -v
```

Expected: pass.

- [ ] **Step 5: Add skip-safe PostgreSQL dirty scope integration tests**

Extend `tests/test_runtime_infrastructure_postgres_integration.py` to cover:

- pending coalescing under the partial unique index;
- claim with `for update skip locked`;
- processing supersede with a newer `source_version`;
- stale complete rejection;
- retry scheduling after failure.

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_postgres_integration -v
```

Expected: skip without `FIN_OPS_TEST_DATABASE_URL`, pass with a disposable PostgreSQL test database.

- [ ] **Step 6: Commit dirty scope repository**

```bash
git add backend/src/fin_ops_platform/services/read_model_dirty_scope_repository.py tests/test_read_model_dirty_scope_repository.py tests/test_runtime_infrastructure_postgres_integration.py
git commit -m "feat: add read model dirty scope repository"
```

## Task 4: Add Worker Runtime and CLI

**Files:**
- Create: `backend/src/fin_ops_platform/services/runtime_worker.py`
- Create: `backend/src/fin_ops_platform/tools/run_runtime_worker.py`
- Create: `tests/test_runtime_worker.py`
- Modify: `backend/README.md`

- [ ] **Step 1: Write worker tests**

Cover:

- One-shot exits when no event is claimed.
- Claimed event dispatches to registered handler and completes on success.
- Handler exception records failure and schedules retry.
- Unknown event type fails permanent with clear error.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker -v
```

Expected: fail because worker module does not exist.

- [ ] **Step 3: Implement runtime worker**

Create a small registry:

```python
RuntimeEventHandler = Callable[[RuntimeQueueEvent], dict[str, object] | None]
```

Add `RuntimeWorker.run_once()` and `RuntimeWorker.run_forever(poll_interval_seconds=5)`.

- [ ] **Step 4: Implement CLI**

CLI options:

- `--once`
- `--poll-interval-seconds`
- `--worker-id`
- `--event-type` repeatable filter

The CLI should build `PostgresConnection(PostgresSettings.from_env())`, create repositories, and run the worker. It should not import `app.server` or construct `Application`.

- [ ] **Step 5: Run worker tests and CLI smoke**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.run_runtime_worker --help
```

Expected: tests pass; help prints without requiring database connection.

- [ ] **Step 6: Commit worker runtime**

```bash
git add backend/src/fin_ops_platform/services/runtime_worker.py backend/src/fin_ops_platform/tools/run_runtime_worker.py tests/test_runtime_worker.py backend/README.md
git commit -m "feat: add runtime worker entrypoint"
```

## Task 5: Add Redis Runtime Helper

**Files:**
- Create: `backend/src/fin_ops_platform/services/redis_runtime.py`
- Create: `tests/test_runtime_infrastructure_helpers.py`
- Modify: `docs/dev/backend.md`

- [ ] **Step 1: Write Redis helper tests**

Cover:

- Missing `FIN_OPS_REDIS_URL` returns disabled health.
- Missing redis package returns unavailable health without raising during app import.
- `get_json`/`set_json` are no-ops or return miss when disabled.
- `publish(channel, payload)` is best effort.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_helpers -v
```

Expected: fail because helper does not exist.

- [ ] **Step 3: Implement Redis helper**

Do lazy import inside connection creation. Public API:

- `RedisRuntimeSettings.from_env()`
- `RedisRuntimeClient.health_summary()`
- `get_json(key)`
- `set_json(key, value, ttl_seconds)`
- `delete(key)`
- `publish(channel, payload)`

Disabled/unavailable Redis must never raise from health or cache methods.

- [ ] **Step 4: Run helper tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_helpers -v
```

Expected: pass.

- [ ] **Step 5: Commit Redis helper**

```bash
git add backend/src/fin_ops_platform/services/redis_runtime.py tests/test_runtime_infrastructure_helpers.py docs/dev/backend.md
git commit -m "feat: add optional redis runtime helper"
```

## Task 6: Add Object Storage Interface

**Files:**
- Create: `backend/src/fin_ops_platform/services/object_storage.py`
- Modify: `tests/test_runtime_infrastructure_helpers.py`
- Modify: `backend/README.md`
- Modify: `docs/operations/deployment.md` if it exists

- [ ] **Step 1: Write object storage settings tests**

Cover:

- `OBJECT_STORAGE_BACKEND=disabled` returns disabled settings.
- `OBJECT_STORAGE_BACKEND=s3` requires endpoint, bucket, access key, and secret key.
- Redacted health does not expose secret key.
- Interface exposes `put_object`, `get_object`, `delete_object`, `head_object`, but default disabled implementation fails fast for write/read.

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_helpers -v
```

Expected: fail for object storage cases.

- [ ] **Step 3: Implement object storage protocol and settings**

Do not implement production S3 upload yet unless no dependency is needed. Define the interface and settings so Module 3 can attach implementation cleanly.

- [ ] **Step 4: Update docs**

Document:

- `OBJECT_STORAGE_BACKEND`
- `S3_ENDPOINT_URL`
- `S3_BUCKET`
- `S3_REGION`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`

State clearly: Module 1 only adds config/interface; file upload cutover is Module 3.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_helpers -v
```

Expected: pass.

- [ ] **Step 6: Commit object storage interface**

```bash
git add backend/src/fin_ops_platform/services/object_storage.py tests/test_runtime_infrastructure_helpers.py backend/README.md docs/dev/backend.md docs/operations/deployment.md
git commit -m "feat: add object storage runtime boundary"
```

## Task 7: Add Health Summary Integration

**Files:**
- Modify: `backend/src/fin_ops_platform/services/runtime_queue.py`
- Modify: `backend/src/fin_ops_platform/services/read_model_dirty_scope_repository.py`
- Modify: `backend/src/fin_ops_platform/services/runtime_worker.py`
- Create: `backend/src/fin_ops_platform/tools/runtime_infrastructure_health.py`
- Modify: `tests/test_runtime_queue.py`
- Modify: `tests/test_read_model_dirty_scope_repository.py`
- Create: `tests/test_runtime_infrastructure_health.py`

- [ ] **Step 1: Write health summary tests**

Cover:

- Queue summary returns pending/processing/failed count and max age.
- Dirty scope summary returns pending/processing/failed count and max stale age.
- Worker heartbeat upsert does not expose secrets.
- Health CLI `--help` does not require PostgreSQL.
- Health CLI JSON includes queue, dirty scopes, worker heartbeat, Redis health, and ObjectStorage config health when dependencies are faked.

- [ ] **Step 2: Run tests to verify failure**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_read_model_dirty_scope_repository tests.test_runtime_worker tests.test_runtime_infrastructure_health -v
```

Expected: fail until summary methods are implemented.

- [ ] **Step 3: Implement summaries**

Use SQL aggregate queries. Avoid loading full queue rows.

- [ ] **Step 4: Implement health CLI**

Create `backend/src/fin_ops_platform/tools/runtime_infrastructure_health.py`.

CLI options:

- `--pretty`
- `--include-postgres` default true
- `--skip-postgres` for local config-only checks

Output JSON fields:

```json
{
  "queue": {},
  "dirty_scopes": {},
  "workers": {},
  "redis": {},
  "object_storage": {}
}
```

The CLI must not expose database passwords, Redis credentials, S3 secret keys, or raw payloads.

- [ ] **Step 5: Run tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_queue tests.test_read_model_dirty_scope_repository tests.test_runtime_worker tests.test_runtime_infrastructure_health -v
```

Expected: pass.

- [ ] **Step 6: Run health CLI smoke**

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_infrastructure_health --skip-postgres --pretty
```

Expected: prints JSON with Redis and ObjectStorage config health, without requiring a PostgreSQL connection.

- [ ] **Step 7: Commit health summaries**

```bash
git add backend/src/fin_ops_platform/services/runtime_queue.py backend/src/fin_ops_platform/services/read_model_dirty_scope_repository.py backend/src/fin_ops_platform/services/runtime_worker.py backend/src/fin_ops_platform/tools/runtime_infrastructure_health.py tests/test_runtime_queue.py tests/test_read_model_dirty_scope_repository.py tests/test_runtime_worker.py tests/test_runtime_infrastructure_health.py
git commit -m "feat: expose runtime infrastructure health summaries"
```

## Task 8: Final Module 1 Verification

**Files:**
- Modify only if verification reveals issues.

- [ ] **Step 1: Run focused unit tests**

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_postgres_migrations \
  tests.test_runtime_queue \
  tests.test_read_model_dirty_scope_repository \
  tests.test_runtime_worker \
  tests.test_runtime_infrastructure_helpers \
  tests.test_runtime_infrastructure_health \
  -v
```

Expected: pass.

- [ ] **Step 2: Run backend check**

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

Expected: readiness JSON prints. If local env lacks production dependencies, record exact failure and run the smallest available alternative.

- [ ] **Step 3: Run migration plan smoke**

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.postgres plan --migrations-dir backend/src/fin_ops_platform/postgres/migrations
```

Expected: command succeeds offline and includes `0009 pending runtime_infrastructure` when no database URL is supplied.

- [ ] **Step 4: Run worker help smoke**

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.run_runtime_worker --help
```

Expected: command prints help without opening PostgreSQL connection.

- [ ] **Step 5: Run runtime infrastructure health smoke**

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_infrastructure_health --skip-postgres --pretty
```

Expected: command prints JSON without opening PostgreSQL connection and without exposing secrets.

- [ ] **Step 6: Run skip-safe PostgreSQL integration tests**

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_infrastructure_postgres_integration -v
```

Expected: skips safely without `FIN_OPS_TEST_DATABASE_URL`; passes when a disposable PostgreSQL test database is configured.

- [ ] **Step 7: Check git status**

```bash
git status --short
```

Expected: clean after all task commits.

## Module 2 Planning Gate

After Module 1 is verified and committed, create the next plan:

```text
docs/superpowers/plans/2026-05-21-runtime-sql-read-model-convergence-module-2-lightweight-bootstrap.md
```

Use the Module 2 `/goal` prompt from the spec and repeat the same process:

- Write detailed bite-sized plan.
- Run plan review.
- Execute only after plan approval.
- Verify and commit before moving to Module 3.
