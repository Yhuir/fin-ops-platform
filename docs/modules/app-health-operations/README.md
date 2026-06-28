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
- `backend/src/fin_ops_platform/services/app_status_job_registry.py`
- `backend/src/fin_ops_platform/services/app_status_dependency_registry.py`

## 当前边界

本模块维护全局运行状态的读侧投影和运维只读 dashboard：

- `/api/app-health`：面向页面和 App Status provider 的运行健康 snapshot，包含 session/runtime、background jobs、dependencies、alerts、worker/job 状态和 `app_status`；不再包含 `workbench_read_model` 或 `workbench_relation_read_model`。
- `/api/app-health/stream`：SSE snapshot/heartbeat，只负责通知 UI 更新状态，不替代 durable facts。
- `/api/operations/app-health-dashboard`：admin-only 只读运维 dashboard，展示数据 inventory、请求性能、runtime outbox/RabbitMQ/worker 指标。
- `/health` / `/health/ready`：公开或探针使用的轻量运行健康摘要；`api_performance.endpoints` 只保留 bounded 最慢 endpoint 摘要，完整 endpoint 明细由 `/metrics` 或 admin-only operations dashboard 提供。
- App Status icon/popover：全局状态入口，只消费后端 `app_status`，不读取当前页面局部 loading，也不展示页面旧同步诊断。
- App Status overview：由 session、background jobs、outbox、worker heartbeat、dependencies、alerts 推导 green/yellow/red。Legacy projection diagnostics 不再进入 domain payload、overall 或 runtime summary。
- Dashboard 发票 inventory 的 `OA 解析` 只统计 OCR 缓存中能识别为正式发票的去重数量；它不展示附件总数、OCR 候选项总数或非正式票据数量。

## 运行事实源

- PostgreSQL runtime queue：`job.outbox_events`；legacy `job.read_model_dirty_scopes` 不再作为 App Status domain/overall 输入。
- Runtime monitoring：`RuntimeMonitoringRepository.app_status_runtime_snapshot()`、`health_summary()` 和 `ready_health_summary()`。这些查询只聚合 outbox、worker heartbeat、RabbitMQ、failed jobs 和 API metrics；legacy dirty scope/readiness 不再作为 `/health`、`/health/ready`、App Status domain/overall 或 runtime summary 输入。ready summary 查询失败必须暴露为 runtime unavailable，不能被空 payload 解释成绿色。
- Worker registry：`runtime_worker_registry.py`。
- Domain/job/dependency registries：`app_status_domain_registry.py`、`app_status_job_registry.py`、`app_status_dependency_registry.py`。
- OA 附件发票 inventory：优先读取 `app.oa_attachment_invoice_cache.invoices`，只保留具备完整发票号码、开票日期、购销方税号、价税合计且 `document_kind` / `invoice_kind` 可判定为正式发票的 OCR 结果，并按强 identity 去重。
- 前端只展示后端事实；不能用当前 route、表格 loading、组件本地状态推导全局状态。

## 关键 fan-out

| 来源 | App Health / Status 影响 | 受影响体验 |
| --- | --- | --- |
| legacy projection missing/stale/refreshing | 不进入 App Health/App Status payload | 迁移期只能在对应 legacy 页面或运维专用诊断中定位；页面读取目标是 direct API |
| legacy projection failed/unavailable | 不进入 App Health/App Status payload | 旧投影失败不再代表页面域不可用；写入是否禁用由 `overall.write_safety` 和具体写 API precondition 决定 |
| required worker missing/stale/mismatch | domain blocked/red 或 busy/yellow | 所有依赖该 worker 的页面不能假设会收敛 |
| outbox backlog | domain busy/yellow；只统计当前有效记录，已被后续 `done` 覆盖的旧 pending/failed 不再进入 backlog/同步中 | 用户看到真实后台处理，而不是被历史队列噪声误导 |
| runtime summary counts | `/api/app-health.app_status.runtime_summary` 聚合 worker、queue 状态 | 左上角 popover 和 `/operations/app-health` 必须能直接看出 active/working/stale/missing、pending/processing/failed/backlog |
| background job queued/running/attention | overall/domain busy 或 attention | 导入、数据重置、ETC、worker task 状态可见 |
| dependency unavailable | blocked/red 或 degraded | OA/session/PostgreSQL/RabbitMQ/Redis 等依赖异常可见 |
| dashboard metrics refetch 失败 | dashboard 保留上一份 payload 并显示 stale warning | 运维读侧不中断，但不能作为 current 事实 |

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或旧同步诊断字段变化。
- 业务状态、UI 状态、legacy projection/worker 下线状态或状态流转变化。
- 跨页面 runtime signal、domain event、derived lifecycle、affected scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护系统状态页 Spec-first Browser 业务验收合同。
- `e2e-coverage.md`：维护系统状态页 Spec-first 合同到自动化覆盖的映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
