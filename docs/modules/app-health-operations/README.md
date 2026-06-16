# 系统状态模块维护入口

- Module key: `app-health-operations`
- 类型：页面模块 / 全局运行状态 plane
- Route: `/operations/app-health`
- Page key: `app-health-operations`

## 修改前必读

- `docs/product-specs/platform-settings-health.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/operations/monitoring.md`
- `docs/operations/deployment.md`
- `docs/dev/api-contracts.md`
- `docs/dev/testing-closure-dependency-map.md`
- `docs/modules/read-models/README.md`
- `docs/modules/runtime-workers/README.md`
- `docs/modules/settings/README.md`

## 代码入口

- `web/src/pages/AppHealthOperationsPage.tsx`
- `web/src/features/appHealth/*`
- `web/src/features/appStatus/*`
- `web/src/contexts/AppHealthStatusContext.tsx`
- `web/src/components/shell/AppStatusIndicator.tsx`
- `backend/src/fin_ops_platform/app/server.py` 中 `/api/app-health*`、`/api/operations/app-health-dashboard`
- `backend/src/fin_ops_platform/services/app_health_service.py`
- `backend/src/fin_ops_platform/services/app_health_alert_service.py`
- `backend/src/fin_ops_platform/services/app_status_overview_service.py`
- `backend/src/fin_ops_platform/services/runtime_monitoring.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
- `backend/src/fin_ops_platform/services/app_status_job_registry.py`
- `backend/src/fin_ops_platform/services/app_status_dependency_registry.py`
- `backend/src/fin_ops_platform/tools/app_status_readiness_backfill.py`

## 当前边界

本模块维护全局运行状态的读侧投影和运维只读 dashboard：

- `/api/app-health`：面向页面和 App Status provider 的运行健康 snapshot，包含 workbench/read model、background jobs、dependencies、alerts、`app_status`。
- `/api/app-health/stream`：SSE snapshot/heartbeat，只负责通知 UI 更新状态，不替代 durable facts。
- `/api/operations/app-health-dashboard`：admin-only 只读运维 dashboard，展示数据 inventory、请求性能、runtime outbox/RabbitMQ/read model/worker 指标。
- `/health` / `/health/ready`：公开或探针使用的轻量运行健康摘要；`api_performance.endpoints` 只保留 bounded 最慢 endpoint 摘要，完整 endpoint 明细由 `/metrics` 或 admin-only operations dashboard 提供。
- App Status icon/popover：全局状态入口，只消费后端 `app_status`，不读取当前页面局部 loading。
- App Status overview：由 session、background jobs、read model readiness、dirty scopes、outbox、worker heartbeat、dependencies、alerts 推导 green/yellow/red。

## 运行事实源

- PostgreSQL durable queue：`job.outbox_events`、`job.read_model_dirty_scopes`。
- Runtime monitoring：`RuntimeMonitoringRepository.app_status_runtime_snapshot()` 和 `health_summary()`。
- Readiness：`read_model.app_status_readiness` 或 Workbench active generation 等价 readiness。
- Worker registry：`runtime_worker_registry.py`。
- Domain/read model/job/dependency registries：`app_status_*_registry.py`。
- 前端只展示后端事实；不能用当前 route、表格 loading、组件本地状态推导全局状态。

## 关键 fan-out

| 来源 | App Health / Status 影响 | 受影响体验 |
| --- | --- | --- |
| read model missing/stale/refreshing | domain busy/yellow，暴露 scope diagnostics | 对应页面显示刷新中，App Status hover 可定位 |
| critical read model failed/unavailable | domain blocked/red，暴露 current-effective scope diagnostics | 对应页面不能假装 fresh；普通 read model failure 不进入全局写闸门，写入是否禁用由 `overall.write_safety` 和具体写 API precondition 决定 |
| required worker missing/stale/mismatch | domain blocked/red 或 busy/yellow | 所有依赖该 worker 的页面不能假设会收敛 |
| dirty scope/outbox backlog | domain busy/yellow | 用户看到后台刷新，而不是旧数据 fresh |
| background job queued/running/attention | overall/domain busy 或 attention | 导入、数据重置、ETC、worker rebuild 状态可见 |
| dependency unavailable | blocked/red 或 degraded | OA/session/PostgreSQL/RabbitMQ/Redis 等依赖异常可见 |
| dashboard metrics refresh 失败 | dashboard 保留上一份 payload 并显示 stale warning | 运维读侧不中断，但不能作为 fresh 事实 |

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
