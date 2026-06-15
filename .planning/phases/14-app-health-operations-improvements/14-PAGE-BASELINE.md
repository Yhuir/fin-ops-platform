# 系统状态 / 运维 L1.5 页面基线卡片

## Scope

- Phase: `14-app-health-operations-improvements`
- Page key: `app-health-operations`
- Route: `/operations/app-health`
- Page entry: `web/src/pages/AppHealthOperationsPage.tsx`
- API clients: `web/src/features/appHealth/*`, `web/src/features/appStatus/*`
- Related frontend: `web/src/contexts/AppHealthStatusContext.tsx`, `web/src/components/shell/AppStatusIndicator.tsx`
- Backend entrypoints: `backend/src/fin_ops_platform/app/server.py` `/api/app-health*`, `/api/operations/app-health-dashboard`
- Core services: `app_health_service.py`, `app_health_alert_service.py`, `app_status_overview_service.py`, `runtime_monitoring.py`, `app_status_*_registry.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

系统状态模块维护全局运行状态的读侧投影和运维只读 dashboard。它不是业务事实源，而是 session、background jobs、read model readiness、dirty scopes、outbox、worker heartbeat、dependencies 和 alerts 的统一观察面。

当前关键边界：

1. `/api/app-health` 面向页面和 App Status provider，包含 workbench/read model、background jobs、dependencies、alerts、`app_status`。
2. `/api/app-health/stream` 是 SSE snapshot/heartbeat，只通知 UI 更新状态，不替代 durable facts。
3. `/api/operations/app-health-dashboard` 是 admin-only 只读 dashboard。
4. App Status icon/popover 只消费后端 `app_status`，不读取当前页面局部 loading。
5. 前端只展示后端事实，不能用当前 route、表格 loading 或组件本地状态推导全局状态。

## Cross-Page Dependencies

- Observes all domains:
  - import pages
  - workbench relation core pages
  - invoice lifecycle/tax pages
  - ETC pages
  - settings/data reset
- Does not own business writes, but its write safety/status signals affect user trust across all pages.
- Phase 0 dependency group: `Analytics and status` / global runtime plane。

## Read Model / Worker / App Status

- Durable facts:
  - `job.outbox_events`
  - `job.read_model_dirty_scopes`
  - `read_model.app_status_readiness`
  - Workbench active generation equivalent readiness
- Services/registries:
  - `RuntimeMonitoringRepository.app_status_runtime_snapshot()`
  - `health_summary()`
  - `runtime_worker_registry.py`
  - `app_status_domain_registry.py`
  - `app_status_read_model_registry.py`
  - `app_status_job_registry.py`
  - `app_status_dependency_registry.py`
- Freshness rule: App Status must derive from durable facts and registries; dashboard stale payload must be labeled stale, not treated as fresh operational truth.

## Current Gaps To Assess Before L2

- 用户要完善的是 App Status icon/popover、系统状态页、SSE、admin dashboard、alerts，还是 write safety。
- global status 是否仍混入当前页面 local loading。
- dashboard metrics refresh 失败时是否保留上一份 payload 并显示 stale warning。
- domain blocked/red 与普通 read model failure/write safety 的边界是否清晰。
- 新增 read model/worker/page 时 registry、manifest、tests、docs 是否同步。

## Risks

- 权限: dashboard admin-only，普通 App Status 可见范围需要限制敏感数据。
- 审计: 运维操作、数据重置、worker 管理如存在写入必须审计；当前 dashboard 应保持只读。
- stale/fresh: dashboard stale payload、SSE heartbeat、readiness 和 dirty scopes 容易被误读。
- 跨页刷新: 所有页面依赖 App Status 定位刷新、失败和 worker 状态。
- worker: worker missing/stale/mismatch 必须准确显示，不能被前端 loading 掩盖。
- 导出: 如 dashboard 支持导出，需避免泄露敏感运行数据。
- 历史数据: readiness backfill 或清理不能把历史 dirty scope/outbox 误标 fresh。

## Test Entry Points

- Backend:
  - `tests/test_app_health_*`
  - `tests/test_app_status_*`
  - runtime monitoring、registry、readiness、dashboard 相关测试
- Frontend:
  - `web/src/test/AppHealth*.test.tsx`
  - App Status indicator/provider 相关测试
- Integration candidates:
  - read model stale -> App Status yellow/domain busy -> page shows refreshing
  - worker missing -> domain blocked/red -> dashboard diagnostics visible

## Seven-Category Test Matrix

- Business core unit tests: 部分适用。主要覆盖 status classification、write safety 规则和 domain severity 映射。
- Service-layer tests: 适用。覆盖 app health service、overview service、runtime monitoring、registries、alerts。
- API contract tests: 适用。覆盖 `/api/app-health`、SSE snapshot、dashboard、权限、stale warning。
- Read model/cache/background job tests: 适用。覆盖 dirty scopes、outbox、readiness、worker heartbeat、dashboard stale payload。
- Frontend component/interaction tests: 适用。覆盖 icon/popover、状态页、SSE 更新、admin dashboard、error/stale。
- End-to-end business-flow integration tests: 适用。保护业务页 stale/worker failure 到 App Status 可见的关键路径。
- Existing feature regression tests: 适用。保护所有页面对 App Status 的消费、权限和写安全提示。

## Docs Impact Entry

- Module docs: `docs/modules/app-health-operations/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/platform-settings-health.md`
  - `docs/operations/runtime-worker-governance.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/operations/monitoring.md`
  - `docs/operations/deployment.md`
  - `docs/dev/api-contracts.md`
- 新增 read model、worker、domain 或 dashboard 指标时必须同步 registry 和长期运维文档。

## Legacy / Transitional Paths

- SSE 只通知 UI 更新，不替代 durable facts。
- App Status 不读取当前页面局部 loading。
- 普通 read model failure 不应自动进入全局写闸门；写入是否禁用由 `overall.write_safety` 和具体 API precondition 决定。
- dashboard stale payload 必须有 stale warning。

## L2 Questions

- 本轮完善目标是状态分类、dashboard、SSE、alerts、权限，还是 registry 覆盖？
- 是否存在前端用 local loading 推导 global status 的旧逻辑必须删除？
- write safety 的 global/domain/API precondition 边界是否需要重新定义？
- dashboard 是否要新增指标；新增指标的事实源和权限是什么？
- 新增页面 phase 后是否需要同步 App Status registry coverage？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确运行事实源、status contract、权限、registry、旧逻辑删除、测试矩阵和文档影响。
