# Workbench Realtime Read Model Load Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让关联工作台在 read model 后台刷新期间可见、可追踪、可自动更新，用户不再需要反复刷新浏览器。

**Architecture:** 首屏继续读取 `/api/workbench/summary` 和 `/api/workbench/groups?detail_level=summary`，请求线程只读稳定 SQL read model。刷新状态来自 `/api/workbench/refresh-status`，SSE `/api/workbench/events` 推送状态变化，前端收到版本或状态变化后自动刷新当前查询页并保留已有数据。

**Tech Stack:** Python custom HTTP server, PostgreSQL read model repository, existing runtime queue/dirty scope tables, React + TypeScript + Vite, EventSource/SSE fallback polling.

---

### Task 1: Document The Runtime Contract

**Files:**
- Modify: `docs/product-specs/workbench.md`
- Modify: `docs/product-specs/app-health-and-background-jobs.md`
- Modify: `docs/dev/api-contracts.md`
- Modify: `docs/operations/monitoring.md`

- [ ] **Step 1: Add the workbench refresh status contract**

Document that `/api/workbench/refresh-status?month=all` is the lightweight status source and returns `read_model_status`, `scope_key`, `generated_at`, `dirty_scopes`, `running_scopes`, `processed_count`, `total_count`, `worker_lag_seconds`, `last_error`, and `retryable`. Unknown counts must be `null`, not `0`.

- [ ] **Step 2: Add the workbench SSE contract**

Document `GET /api/workbench/events?month=all`, event names, fallback polling, and the rule that events notify status/version changes while data still comes from summary/groups APIs.

- [ ] **Step 3: Add monitoring guidance**

Document how to diagnose stale read model, failed dirty scopes, worker heartbeat lag, Redis cache misses, and SSE fallback.

### Task 2: Backend Refresh Status And Events

**Files:**
- Modify: `backend/src/fin_ops_platform/app/server.py`
- Test: `tests/test_workbench_sql_runtime.py`

- [ ] **Step 1: Add failing backend tests**

Add tests that:
- `/api/workbench/refresh-status` normalizes failed dirty scopes to `read_model_status=failed` and exposes `last_error`.
- `/api/workbench/events` returns a `text/event-stream` response and emits a `workbench.read_model.*` event with the same normalized payload.

- [ ] **Step 2: Normalize refresh status in one helper**

Create an Application helper that takes repository payload and returns stable fields:
- `read_model_status`: `fresh`, `refreshing`, `stale`, `failed`, or `unavailable`.
- `scope_key`
- `generated_at`
- `read_model_version`
- `dirty_scopes`
- `running_scopes`
- `processed_count`
- `total_count`
- `worker_lag_seconds`
- `last_error`
- `retryable`

- [ ] **Step 3: Add `/api/workbench/events`**

Route `GET /api/workbench/events?month=all` to a handler that resolves session, emits current refresh status as SSE, emits heartbeat, sleeps 5 seconds, and reuses `AppHealthService.serialize_sse_event`.

- [ ] **Step 4: Run targeted backend tests**

Run:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
```

Expected: PASS.

### Task 3: Frontend Workbench Status API

**Files:**
- Modify: `web/src/features/workbench/types.ts`
- Modify: `web/src/features/workbench/api.ts`
- Test: `web/src/test/WorkbenchApiRuntimePath.test.ts`

- [ ] **Step 1: Add TypeScript types**

Add `WorkbenchRefreshStatus`, `WorkbenchRefreshStatusEvent`, and normalize fields from snake_case/camelCase payloads.

- [ ] **Step 2: Add fetch and subscribe helpers**

Add `fetchWorkbenchRefreshStatus(month, signal)` and `subscribeWorkbenchRefreshEvents(month, onEvent, onError)`. EventSource must use `apiUrl("/api/workbench/events?...")` and fallback to `null` when EventSource is unavailable.

- [ ] **Step 3: Add API tests**

Assert runtime path uses `/fin-ops-api/api/workbench/refresh-status` and `/fin-ops-api/api/workbench/events`.

### Task 4: Frontend No-Refresh Auto Update

**Files:**
- Modify: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- Modify: `web/src/app/styles.css`
- Test: `web/src/test/WorkbenchSelection.test.tsx` or a focused workbench page test already covering initial load

- [ ] **Step 1: Track refresh status**

Add component state for workbench refresh status. Initial load can set it from summary/groups page status; SSE/polling keeps it current.

- [ ] **Step 2: Display concise status**

Show a small workbench read model status area:
- fresh: `数据已最新`
- refreshing/stale: `关联台正在刷新`
- failed: `关联台刷新失败`
- unavailable: `关联台读模型不可用`

Include progress when known and last error when present. Do not clear existing groups during refreshing/stale.

- [ ] **Step 3: Subscribe to events with fallback polling**

Use `subscribeWorkbenchRefreshEvents`. If unavailable or errors, poll `/api/workbench/refresh-status` every 5 seconds and on window focus. Debounce data reloads and abort older requests.

- [ ] **Step 4: Refetch current page on version/status completion**

When event status becomes `fresh`, or when `generated_at/read_model_version` changes, call existing `loadWorkbenchData(..., { background: true, zoneQueries })`. Avoid duplicate reloads for the same version.

- [ ] **Step 5: Run frontend tests**

Run:

```bash
cd web && npm test -- WorkbenchApiRuntimePath
cd web && npm test -- WorkbenchSelection
```

Expected: PASS.

### Task 5: Verification And Performance Sanity

**Files:**
- No required code files.

- [ ] **Step 1: Run targeted backend and frontend tests**

Run the targeted test commands from Tasks 2 and 4.

- [ ] **Step 2: Run build**

Run:

```bash
cd web && npm run build
```

Expected: PASS.

- [ ] **Step 3: Confirm payload discipline**

Inspect or test that `fetchWorkbenchInitialPage` uses summary + groups summary, not old `/api/workbench` full payload.

- [ ] **Step 4: Summarize residual risk**

If tests or environment-dependent checks cannot run, report exact command and failure reason.

## Self-Review

- Spec coverage: The plan covers status contract, SSE, fallback polling, auto-refresh, stale/failed visibility, docs, tests, and payload discipline.
- Placeholder scan: No task uses "TBD", "TODO", or unspecified "appropriate handling"; unknown numeric progress is explicitly `null`.
- Type consistency: `WorkbenchRefreshStatus`, event payloads, `read_model_status`, `generated_at`, and `read_model_version` are named consistently across backend, API, and page tasks.
