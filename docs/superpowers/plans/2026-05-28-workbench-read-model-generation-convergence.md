# Workbench Read Model Generation Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让关联工作台只读取稳定 active generation，后台 read model 重建期间不再暴露半成品，刷新页面数量不再漂移。

**Architecture:** 为 workbench read model 增加 generation 元数据和 `generation_id` 列。后台投影先写入 building generation，校验成功后单事务切换 active generation；API、Redis cache、SSE 状态和前端刷新都绑定 active generation。Redis key 使用 generation 隔离，worker/AppHealth 暴露 failed/stale/lag。

**Tech Stack:** Python custom HTTP server, PostgreSQL migrations/repository, runtime dirty scope queue, Redis TTL page cache, React + TypeScript + Vite.

---

## Current Audit Findings

- `PostgresReadModelRepository.save_workbench_read_models` currently deletes `read_model.workbench_rows`, `workbench_groups`, `workbench_group_rows`, and `workbench_summary` by `scope_key` before inserting replacements.
- `_refresh_workbench_all_scope_from_month_shards` also deletes all `scope_key='all'` rows before rebuilding the aggregate.
- Existing unique indexes are scoped by `scope_key`/`zone`/`group_id`, not `generation_id`, so building and active versions cannot coexist.
- `/api/workbench/groups` Redis cache is versioned by repository cache version/schema, but not by an explicit active generation id.
- This explains user-visible count drift during refresh: page reads can observe a scope between delete and full rebuild, or observe all-scope aggregation while month shards are changing.

### Task 1: Add Generation Schema

**Files:**
- Create: `backend/src/fin_ops_platform/postgres/migrations/0034_workbench_generation_convergence.sql`
- Modify: `tests/test_postgres_migrations.py`

- [ ] **Step 1: Add `read_model.workbench_generations`**

Create columns: `generation_id`, `tenant_id`, `scope_key`, `status`, `source_versions`, `schema_version`, timestamps, count fields, `checksum`, `last_error`, `build_metadata`.

- [ ] **Step 2: Add `generation_id` to workbench read tables**

Add `generation_id` to `workbench_summary`, `workbench_snapshots`, `workbench_rows`, `workbench_groups`, and `workbench_group_rows`. Backfill existing rows with deterministic `legacy:{scope_key}` generation ids and create active generation rows for existing data.

- [ ] **Step 3: Add generation-aware indexes**

Create active generation unique index and hot path indexes containing `generation_id`.

### Task 2: Repository Generation Helpers

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Test: `tests/test_workbench_sql_runtime.py`

- [ ] **Step 1: Add tests first**

Cover:
- API reads active generation when active and building rows coexist.
- Failed generation does not become active and exposes `last_error`.
- Redis cache version uses active generation.

- [ ] **Step 2: Add helper methods**

Implement helpers to resolve active generation, start building generation, activate generation, fail generation, and return generation metadata.

### Task 3: Atomic Generation Writes

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Test: `tests/test_workbench_sql_runtime.py`

- [ ] **Step 1: Write into generation-specific rows**

`save_workbench_read_models` must insert new payloads with a new building generation id and avoid deleting the active generation first.

- [ ] **Step 2: Activate only after all inserts succeed**

Activation marks previous active as superseded and new generation as active inside the same transaction.

- [ ] **Step 3: Preserve active generation on failure**

Exceptions mark the building generation failed and leave the previous active generation untouched.

### Task 4: Active-Generation Read APIs And Redis Cache

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_sql_runtime.py`

- [ ] **Step 1: Pin summary/groups/detail queries to active generation**

Every workbench hot path query must filter by active generation id when one exists.

- [ ] **Step 2: Include generation in API payloads**

Return `active_generation_id` and `read_model_version` from summary, groups, detail, refresh-status, and events.

- [ ] **Step 3: Include generation in Redis cache keys**

Redis keys must include active generation id. Old keys expire by TTL and cannot pollute a new generation.

### Task 5: Worker Health And Monitoring

**Files:**
- Modify: `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- Modify: `backend/src/fin_ops_platform/services/app_health_service.py` if needed
- Test: `tests/test_runtime_monitoring.py` or `tests/test_workbench_sql_runtime.py`

- [ ] **Step 1: Expose generation and worker lag status**

Refresh status returns `active_generation_id`, `building_generation_id`, failed generation, dirty scopes, worker lag, and last error.

- [ ] **Step 2: Treat stale worker lag as unhealthy**

Document and test lag thresholds where possible; keep PostgreSQL dirty scope/outbox as source of failure truth.

### Task 6: Frontend Generation Awareness

**Files:**
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Test: `web/src/test/WorkbenchApiRuntimePath.test.ts`
- Test: `web/src/test/WorkbenchSelection.test.tsx`

- [ ] **Step 1: Carry active generation ids through types**

Map `active_generation_id` and `read_model_version`.

- [ ] **Step 2: Reload exactly once on generation switch**

Do not merge building-generation data into visible state. When SSE/status reports a new active generation, background reload current query once.

### Task 7: Verification Tool And Docs

**Files:**
- Create: `backend/src/fin_ops_platform/tools/validate_workbench_generation_convergence.py`
- Modify: `docs/product-specs/workbench.md`
- Modify: `docs/product-specs/app-health-and-background-jobs.md`
- Modify: `docs/dev/api-contracts.md`
- Modify: `docs/operations/monitoring.md`
- Modify: `ARCHITECTURE.md`

- [ ] **Step 1: Add JSON validation tool**

The tool repeatedly calls summary and groups endpoints, records generation ids/counts/durations, and fails when counts vary under the same generation.

- [ ] **Step 2: Document production runbook**

Document generation semantics, Redis key rules, worker lag thresholds, and sidecar/search-engine decision gate.

## Verification Commands

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_monitoring -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
cd web && npm test -- WorkbenchApiRuntimePath --run
cd web && npm test -- WorkbenchSelection --run
cd web && npm run build
git diff --check
```

## Self-Review

- Spec coverage: Covers generation schema, atomic publishing, active reads, Redis generation cache, worker health, frontend generation awareness, docs, and validation.
- Placeholder scan: No placeholder tasks; unknown production metrics are handled by explicit validation and staging requirements.
- Type consistency: Uses `generation_id`, `active_generation_id`, and `read_model_version` consistently across repository/API/frontend.
