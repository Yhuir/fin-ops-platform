# AppHealth Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-grade read-only AppHealth operations dashboard with import inventory, real-time API/DB percentiles, and RabbitMQ/outbox/worker/read-model runtime metrics.

**Architecture:** Keep existing `/api/app-health` unchanged for global health and add `GET /api/operations/app-health-dashboard` as an admin-only read model for operations UI. Backend collectors aggregate PostgreSQL, in-process rolling API metrics, runtime queue tables, and RabbitMQ management metrics into a small typed payload; frontend replaces the old operations/action page with concise MUI dashboard cards and tables. Unknown or unavailable metrics are represented as `null`/`unknown`, never as fake zeroes.

**Tech Stack:** Python stdlib backend, existing PostgreSQL connection abstraction, existing RabbitMQ runtime helpers, React + TypeScript + MUI, Vitest/Testing Library, `python3 -m unittest`.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-05-23-app-health-dashboard-design.md`
- Product docs: `docs/product-specs/app-health-and-background-jobs.md`
- API docs: `docs/dev/api-contracts.md`
- Ops docs: `docs/operations/monitoring.md`

## File Structure

- Create `backend/src/fin_ops_platform/services/operations_dashboard.py`
  - Owns dashboard payload assembly, data inventory SQL, API percentile formatting, runtime row shaping, and warning collection.
- Modify `backend/src/fin_ops_platform/services/runtime_monitoring.py`
  - Add row-level dashboard methods for outbox, queues, read models, and workers while leaving `health_summary()` compatible.
- Modify `backend/src/fin_ops_platform/app/server.py`
  - Add admin-only route `GET /api/operations/app-health-dashboard`.
- Add `tests/test_operations_dashboard_service.py`
  - Unit-tests payload shape, data source status handling, percentiles, and no-fake-zero behavior with fake DB/provider objects.
- Add or extend `tests/test_app_health_api.py`
  - Verifies new route auth/admin behavior and that `/api/app-health` stays unchanged.
- Modify `web/src/features/appHealth/types.ts`
  - Add `OperationsDashboardPayload` and nested dashboard types.
- Modify `web/src/features/appHealth/api.ts`
  - Add `fetchAppHealthDashboard(signal?)` using existing authenticated `requestJson`.
- Rewrite `web/src/pages/AppHealthOperationsPage.tsx`
  - Remove old Summary/Session/OA Sync/Workbench/Background Jobs/Dependencies/Alerts and all mutation controls.
  - Render import inventory, API/DB performance, and runtime queues/read models/workers.
- Rewrite `web/src/test/AppHealthOperationsPage.test.tsx`
  - Validate concise read-only UI, admin guard, dashboard endpoint use, unknown metrics display, and absence of old operations.
- Modify `web/src/test/apiMock.ts`
  - Add mock response for `/api/operations/app-health-dashboard`.
- Update docs listed above.

## Final Codex Execution Prompt

```text
/goal 生产级重构 AppHealth 运维状态为只读 Dashboard：新增独立 admin-only 接口 GET /api/operations/app-health-dashboard；展示流水/发票/OA 导入数量和最近同步时间；展示进程内 rolling window 的 API/DB p95/p99；展示 PostgreSQL outbox、RabbitMQ queue/DLQ、worker heartbeat、read model refresh/stale 指标；保留 /api/app-health 现有语义；前端移除旧 AppHealth 运维内容和 retry/ack 操作，用现有 MUI 做 HeroUI 风格简洁只读 UI，只有小刷新图标和小号生成时间；不引入 HeroUI，不接时序库，不把 unknown 显示成 0；更新产品/API/运维文档并跑后端/前端相关测试。

执行顺序：
1. 阅读 AGENTS.md、README.md、ARCHITECTURE.md、spec 与现有 app-health/runtime 代码。
2. 先写后端 service/API 测试，再实现 operations_dashboard collector、runtime_monitoring row-level metrics、server route/admin gate。
3. 再写前端页面测试，重写 AppHealthOperationsPage 与 appHealth API/types/mock。
4. 更新 docs/product-specs/app-health-and-background-jobs.md、docs/dev/api-contracts.md、docs/operations/monitoring.md。
5. 运行 python3 -m unittest tests.test_operations_dashboard_service tests.test_app_health_api tests.test_runtime_monitoring -v；运行 npm test -- --run src/test/AppHealthOperationsPage.test.tsx；运行 npm run build；运行 git diff --check。
6. 做完成审计：逐条证明接口、权限、数据口径、p95/p99、RabbitMQ/outbox/worker/read model、UI 字眼、无操作按钮、文档和验证都已满足。
```

## Task 1: Backend Dashboard Service Tests

**Files:**
- Create: `tests/test_operations_dashboard_service.py`
- Read: `backend/src/fin_ops_platform/services/api_performance_metrics.py`
- Read: `backend/src/fin_ops_platform/services/runtime_monitoring.py`

- [ ] Write fake connection/provider tests for `OperationsDashboardService.build_payload()`.
- [ ] Assert `generated_at`, `data_inventory`, `request_performance`, `runtime_performance`, and `freshness.warnings` exist.
- [ ] Assert invoice `total_count` excludes deleted rows in expected SQL/result handling.
- [ ] Assert missing OA attachment inventory returns `count: null`, `status: "unknown"`, and warning `invoice_oa_attachment_inventory_unknown`.
- [ ] Assert API endpoints include configured defaults even when no rolling samples exist, with percentile fields set to `null`.
- [ ] Assert runtime queues output known RabbitMQ routes even when management metrics are unavailable, with `status: "unknown"` and warning `rabbitmq_metrics_unavailable`.
- [ ] Run:
  ```bash
  PYTHONPATH=backend/src python3 -m unittest tests.test_operations_dashboard_service -v
  ```
  Expected: fail because service does not exist yet.

## Task 2: Backend Dashboard Implementation

**Files:**
- Create: `backend/src/fin_ops_platform/services/operations_dashboard.py`
- Modify: `backend/src/fin_ops_platform/services/runtime_monitoring.py`
- Modify: `backend/src/fin_ops_platform/app/server.py`

- [ ] Implement `OperationsDashboardService(connection, api_performance_recorder, runtime_repository=None).build_payload()`.
- [ ] Implement SQL collectors for bank, invoice, and OA inventory using PostgreSQL aggregate queries only.
- [ ] Normalize timestamps to JSON-serializable ISO strings and preserve `null` for unknown values.
- [ ] Add runtime dashboard methods to `RuntimeMonitoringRepository`:
  - `dashboard_outbox_metric()`
  - `dashboard_queue_metrics()`
  - `dashboard_read_model_metrics()`
  - `dashboard_worker_metrics()`
- [ ] Add route `GET /api/operations/app-health-dashboard` to `server.py`.
- [ ] Gate route with existing session/admin permission checks; unauthenticated uses existing `401`, non-admin returns `403`.
- [ ] Run:
  ```bash
  PYTHONPATH=backend/src python3 -m unittest tests.test_operations_dashboard_service tests.test_app_health_api tests.test_runtime_monitoring -v
  ```
  Expected: pass.

## Task 3: Frontend API Types and Tests

**Files:**
- Modify: `web/src/features/appHealth/types.ts`
- Modify: `web/src/features/appHealth/api.ts`
- Modify: `web/src/test/apiMock.ts`
- Rewrite: `web/src/test/AppHealthOperationsPage.test.tsx`

- [ ] Add TypeScript dashboard payload types matching the backend response.
- [ ] Add `fetchAppHealthDashboard(signal?)` to `web/src/features/appHealth/api.ts`.
- [ ] Add a stable dashboard mock response to `web/src/test/apiMock.ts`.
- [ ] Rewrite page tests to expect:
  - title `AppHealth 运维状态`
  - concise sections `数据`, `请求`, `后台`
  - counts for 流水/发票/OA
  - p95/p99 values for API/DB
  - RabbitMQ/outbox/worker/read model rows
  - `--` for unknown values
  - no retry/ack/acknowledge/background job operation controls
  - request path `/api/operations/app-health-dashboard`, not `/api/app-health`
- [ ] Run:
  ```bash
  cd web && npm test -- --run src/test/AppHealthOperationsPage.test.tsx
  ```
  Expected: fail until the page is rewritten.

## Task 4: Frontend Dashboard Page

**Files:**
- Rewrite: `web/src/pages/AppHealthOperationsPage.tsx`

- [ ] Replace old operations page content with read-only dashboard state.
- [ ] Preserve existing admin guard.
- [ ] Poll every 10 seconds while mounted and avoid overlapping requests.
- [ ] Provide a small refresh icon button and small generated timestamp.
- [ ] Use MUI components only, styled to be clean, compact, and HeroUI-like.
- [ ] Keep copy concise; do not show subtitle, right-side status, or overall normal/degraded/error/sample-insufficient labels.
- [ ] Use color only as a visual emphasis for slow p95/p99 values; do not render ok/warn/critical words.
- [ ] Run:
  ```bash
  cd web && npm test -- --run src/test/AppHealthOperationsPage.test.tsx
  ```
  Expected: pass.

## Task 5: Documentation

**Files:**
- Modify: `docs/product-specs/app-health-and-background-jobs.md`
- Modify: `docs/dev/api-contracts.md`
- Modify: `docs/operations/monitoring.md`

- [ ] Document that Settings AppHealth is now a read-only dashboard.
- [ ] Document the new endpoint contract, permission, and unknown/null semantics.
- [ ] Document the data inventory source of truth and RabbitMQ/outbox metric interpretation.
- [ ] Document that `/api/app-health` remains the global health endpoint and must not be repurposed for the dashboard.

## Task 6: Verification and Completion Audit

**Files:**
- All changed files.

- [ ] Run backend tests:
  ```bash
  PYTHONPATH=backend/src python3 -m unittest tests.test_operations_dashboard_service tests.test_app_health_api tests.test_runtime_monitoring -v
  ```
- [ ] Run frontend test:
  ```bash
  cd web && npm test -- --run src/test/AppHealthOperationsPage.test.tsx
  ```
- [ ] Run frontend build:
  ```bash
  cd web && npm run build
  ```
- [ ] Run diff hygiene:
  ```bash
  git diff --check
  ```
- [ ] Inspect final diffs for secrets, broad refactors, accidental old-operation controls, and changed `/api/app-health` semantics.
- [ ] Completion audit must explicitly prove:
  - Design document exists and was reviewed.
  - Execution prompt with `/goal` exists.
  - New dashboard route exists, is admin-only, and returns only read data.
  - Import inventory covers bank, invoice, OA with explicit unknown handling.
  - Request performance includes p95/p99 API and DB metrics from rolling window.
  - Runtime performance covers outbox, RabbitMQ, workers, and read models.
  - Frontend page removes existing old sections and mutation controls.
  - UI copy matches user constraints.
  - Docs and tests were updated and verification was attempted.
