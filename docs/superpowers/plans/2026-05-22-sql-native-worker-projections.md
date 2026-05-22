# SQL Native Worker Projections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将所有 runtime worker 收敛为 PostgreSQL durable queue + repository-native shard builder，不再通过完整 Application 或 API payload builder 执行生产刷新。

**Architecture:** PostgreSQL facts/projections 是事实源，`job.outbox_events` 与 `job.read_model_dirty_scopes` 是可恢复队列，worker 按 scope shard claim 后直接用 SQL repository 构建 read model 或对象存储迁移结果。Redis 只做短 TTL cache、pub/sub wakeup 和辅助锁；任何 Redis 丢失都不能影响正确性。

**Tech Stack:** Python worker CLI, PostgreSQL, psycopg, `FOR UPDATE SKIP LOCKED`, `read_model.*` tables, MinIO/S3 object storage, Redis helper.

---

## /goal

把 fin-ops-platform 的 7 类 worker 全部升级为 SQL-native production projection worker：不构造完整 Application，不读取 full snapshot，不做 all-scope 巨任务，按 month/entity/page shard 使用 PostgreSQL repository 批量读写，并保持 API 只读 SQL read model / Redis cache。

## Worker Inventory

当前 `backend/src/fin_ops_platform/app/worker.py` 暴露 7 类 worker handler：

1. `file_object.gridfs_migration`：GridFS -> MinIO/S3 per-file migration。
2. `oa.sync`：OA Mongo read-only source -> PostgreSQL OA projections。
3. `workbench.read_model.refresh`：workbench rows/candidates/snapshots refresh。
4. `cost_statistics.read_model.refresh`：成本统计 SQL 聚合 refresh。
5. `tax_offset.read_model.refresh`：税金抵扣 SQL 聚合 refresh。
6. `search.read_model.refresh`：搜索索引 refresh。
7. `pending_invoice.read_model.refresh`：待找发票聚合 refresh。

## Target Rules For Every Worker

- Worker CLI 不为 refresh handler 调用 `build_application()`。
- Worker handler 只接收 repository/cache/object-storage/config，不接收 API `Application`。
- `all` scope 只能展开为子任务，不做大范围同步构建。
- Builder 使用 SQL 查询 facts/read model/projection 表，批量 upsert 目标表。
- 每个 scope 完成后调用 `complete_read_model_refresh`；失败保留 `last_error`，由 queue retry。
- 每个 builder 有 guard test，确认不会调用 API builder、`StateStore.load()` 或旧 snapshot fallback。

## Serial Tasks

### Task 1: Search/Pending Invoice SQL-native Worker

**Files:**
- Create: `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- Modify: `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Modify: `tests/test_search_pending_sql_runtime.py`

- [x] Add failing tests proving `search.read_model.refresh` and `pending_invoice.read_model.refresh` can run with a repository-native builder and without an `Application`.
- [x] Implement `SearchPendingSqlProjectionBuilder` using PostgreSQL connection and `PostgresReadModelRepository`.
- [x] Search builder reads `read_model.workbench_rows` by month scope and writes `read_model.search_index_rows`.
- [x] Pending invoice builder reads `app.bank_transactions`, `app.invoices`, `app.workbench_pair_relations`, `app.bank_transaction_categories`, and `app.app_settings`, then writes `read_model.pending_invoice_rows`.
- [x] Worker CLI creates this builder directly; it must not call `build_application()` for search/pending worker flags.
- [x] Replace `search:all` / `pending_invoice:*:all` large jobs with shard expansion where possible.
- [x] Verify targeted pytest and local PG worker smoke.

### Task 2: Workbench SQL-native Worker

**Files:**
- Create: `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
- Modify: `backend/src/fin_ops_platform/services/workbench_read_model_refresh.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Test: `tests/test_workbench_sql_projection.py`

- [x] Extract the workbench read model build path out of `Application`.
- [x] Builder reads SQL facts, OA projections, OA expense item invoice-like attachments, pair relations, app settings, active row overrides, active exception cases and no-OA relation payload through repositories.
- [x] Worker handles `workbench:month:{YYYY-MM}` only; `all` enqueues monthly shards.
- [x] Upsert `read_model.workbench_rows`, `workbench_snapshots` and `workbench_candidate_matches`; stale source-version writes are rejected at the repository boundary.
- [~] Verify pair relation changes rebuild only affected month scopes. Current smoke proved worker claim/complete, paired materialized OA attachment rows by source OA relation, candidate regeneration, no-OA active relation grouping, active overrides, and active exception projection; full old-builder parity requires an explicit exported legacy JSON comparison.

### Task 3: Cost/Tax SQL-native Aggregation Workers

**Files:**
- Create: `backend/src/fin_ops_platform/services/cost_tax_sql_projection.py`
- Modify: `backend/src/fin_ops_platform/services/cost_statistics_read_model_refresh.py`
- Modify: `backend/src/fin_ops_platform/services/tax_offset_read_model_refresh.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Test: `tests/test_cost_tax_sql_projection.py`

- [x] Implement SQL aggregation builders for cost statistics and tax offset.
- [~] Builders read workbench SQL read model, invoices, certified tax state, OA attachment invoice cache and settings by month. Full pair-relation/fact-native cost parity still needs reconciliation.
- [x] `all` scope enqueues month shards.
- [x] Redis cache is populated after PostgreSQL read model upsert only.
- [~] Add reconciliation tests against the old services on sample data. `scripts/reconcile-runtime-read-models.py` now records SQL read model counts and accepts `--legacy-workbench-json` for shadow old-builder comparison; cost/tax semantic parity still needs sample legacy exports.

### Task 4: OA Sync Sharding Hardening

**Files:**
- Modify: `backend/src/fin_ops_platform/services/oa_projection_sync.py`
- Modify: `backend/src/fin_ops_platform/app/worker.py`
- Test: `tests/test_oa_projection_sql_runtime.py`

- [~] `oa.sync all` honors cutoff-forward months, but still needs durable month-shard fan-out instead of processing all months in one event.
- [x] Monthly shard pulls OA records and invoice attachments according to app settings `oa_import`.
- [x] Attachment projection stores invoice attachment metadata only; screenshot/non-invoice attachments are not exposed as invoice facts.
- [x] OA projection writes dirty scopes for workbench/search/pending invoice.

### Task 5: File Migration Worker Hardening

**Files:**
- Modify: `backend/src/fin_ops_platform/services/file_object_migration.py`
- Test: `tests/test_file_object_migration.py`

- [x] Confirm per-file job idempotency and dedupe.
- [x] Verify size/sha256/etag after object upload.
- [x] Implement/verify orphan temp/final cleanup job.
- [x] Ensure production request path never falls back to GridFS after verified object exists.

### Task 6: Worker Deployment Matrix

**Files:**
- Modify: `docs/operations/deployment.md`
- Modify: `docs/dev/local-development.md`
- Modify: `backend/README.md`

- [x] Document one process per worker role:
  - `worker-oa-sync`
  - `worker-workbench`
  - `worker-search`
  - `worker-pending-invoice`
  - `worker-cost-tax`
  - `worker-file-migration`
- [x] Document event type flags, concurrency, lock timeout and retry settings.
- [x] Document Redis optional behavior and PostgreSQL-only polling fallback.
- [x] Document smoke commands and expected backlog/failed metrics.

### Task 7: Guard Tests And Performance Smoke

**Files:**
- Modify: `tests/test_runtime_state_policy.py`
- Modify: `tests/test_search_pending_sql_runtime.py`
- Modify: `tests/test_workbench_sql_projection.py`

- [x] Add static guard: production worker refresh modules must not import `fin_ops_platform.app.server.build_application`.
- [x] Add static guard: production worker refresh modules must not call `StateStore.load()` or query `state:%`.
- [x] Add local PG smoke for worker claim/complete on search and pending invoice shards.
- [x] Record query plan/index checks for search/pending/workbench/cost/tax hot paths via `scripts/reconcile-runtime-read-models.py --explain` and `docs/operations/runtime-read-model-hardening.md`.

## Parallel Workstreams

- **A: Search/Pending Invoice** - Task 1, highest priority because search/all smoke exposed slow path.
- **B: Workbench** - Task 2 after Task 1 interfaces are stable.
- **C: Cost/Tax** - Task 3 can run parallel with Task 2.
- **D: OA/File** - Tasks 4 and 5 can run parallel after queue contracts are stable.
- **E: Docs/Guard/Smoke** - Tasks 6 and 7 run continuously and must close each task.

## Completion Gate

- No production worker refresh handler calls `build_application()`.
- No production worker refresh handler calls `ApplicationStateStore.load()` or reads `state:*`.
- `search.read_model.refresh all` expands to month/entity shards and does not run a giant synchronous rebuild.
- Redis disabled still allows all workers to complete through PostgreSQL polling.
- Workbench API keeps returning paired rows from SQL read model after backend restart and worker rebuild.
- Search and pending invoice API cache miss enqueues refresh and returns SQL stale/refreshing status, without synchronous scanning.
- Targeted pytest passes; local PG/Redis/MinIO smoke passes; worker backlog/failed metrics are observable.
