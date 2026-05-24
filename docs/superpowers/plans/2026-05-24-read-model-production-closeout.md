# Read Model Production Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the PostgreSQL-native read model closeout for cost statistics, tax offset, pending invoices, no-OA bank batches, and turnover ledger without turning RabbitMQ or Redis into business state.

**Architecture:** PostgreSQL read_model tables become the API hot-read boundary. Worker projections rebuild deterministic row-level tables from app facts or existing structured workbench rows/groups; API routes read rows/aggregates and enqueue refresh on stale/miss. RabbitMQ remains delivery only, backed by PostgreSQL outbox/dirty scopes; Redis remains optional short TTL cache for large read-only payloads.

**Tech Stack:** Python, PostgreSQL migrations, pytest, RabbitMQ runtime worker envelope, Redis helper.

---

### Task 1: Schema Closeout

**Files:**
- Create: `backend/src/fin_ops_platform/postgres/migrations/0022_read_model_native_closeout.sql`
- Modify: `tests/test_postgres_migrations.py`
- Modify: `tests/test_postgres_test_utils.py`
- Modify: `tests/postgres_test_utils.py`

- [x] Add idempotent tables and indexes for `read_model.cost_statistics_rows`, `read_model.tax_offset_items`, `read_model.no_oa_bank_batch_rows`, `read_model.turnover_ledger_rows`.
- [x] Add pending invoice scope/month support without breaking existing rows.
- [x] Add grants for `fin_ops_api`, `fin_ops_worker`, `fin_ops_readonly`, `fin_ops_migrator`.
- [x] Update pinned migration tests to include `0022`.
- [x] Run migration discovery tests.

### Task 2: Cost/Tax SQL-Native Read Models

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/services/cost_tax_sql_projection.py`
- Modify: `tests/test_cost_statistics_sql_runtime.py`
- Modify: `tests/test_tax_offset_sql_runtime.py`

- [x] Write tests proving repository reconstructs cost explorer/month payload from `cost_statistics_rows`.
- [x] Write tests proving tax payload is reconstructed from `tax_offset_items`.
- [x] Implement save/read row methods while preserving compatibility snapshot writes.
- [x] Change cost projection to read structured workbench groups/rows instead of `workbench_snapshots.payload`.
- [x] Run cost/tax runtime tests.

### Task 3: Pending Invoice Monthly Shards

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- Modify: `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Modify: `tests/test_search_pending_sql_runtime.py`

- [x] Add parsing for `direction:filter:YYYY-MM` and legacy `direction:filter`.
- [x] Expand legacy/all pending scopes to month shards in worker handler.
- [x] Save month-specific rows with scoped deletes.
- [x] Preserve API paging/filtering and enqueue behavior.
- [x] Run search/pending runtime tests.

### Task 4: No-OA and Turnover Read Model Boundary

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Add/modify focused tests under `tests/`

- [x] Add read repository methods for no-OA and turnover rows.
- [x] Persist no-OA row read model on durable no-OA snapshot writes.
- [x] Change list APIs to prefer read model rows; cold misses still build via existing domain service and persist/cache rows.
- [x] Keep mutation paths invalidating turnover row read model.
- [x] Run no-OA/turnover focused tests.

Follow-up: move no-OA and turnover cold rebuild into dedicated RabbitMQ worker handlers if those pages become frequent write-after-read paths. The current closeout removes hot-read full scans after warmup but does not introduce new event types.

### Task 5: Operations Closeout

**Files:**
- Modify: `docs/operations/read-model-production-audit-2026-05-24.md`
- Modify: `docs/operations/deployment.md`
- Modify: `docs/operations/monitoring.md`
- Modify deployment templates if necessary.

- [x] Document removing/fixing `fin-ops-worker@oa-rabbitmq.service`.
- [x] Document `pg_stat_statements` preload requirement and post-deploy verification.
- [x] Document migration/deploy/RabbitMQ validation order.
- [x] Run `git diff --check`.
