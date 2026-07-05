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
- `/api/operations/app-health-dashboard`：admin-only 只读运维 dashboard，展示数据 inventory、导入历史、请求性能、runtime outbox/read model/worker 指标。RabbitMQ 管理接口是可选 transport 观测，不是 read model freshness 事实源；dashboard 默认不阻塞等待 RabbitMQ management API，需显式设置 `FIN_OPS_APP_HEALTH_DASHBOARD_RABBITMQ_METRICS=1` 才读取实时队列管理指标。
- `/health` / `/health/ready`：公开或探针使用的轻量运行健康摘要；`api_performance.endpoints` 只保留 bounded 最慢 endpoint 摘要，完整 endpoint 明细由 `/metrics` 或 admin-only operations dashboard 提供。
- App Status icon/popover：全局状态入口，只消费后端 `app_status`，不读取当前页面局部 loading；popover 必须显示 read model、worker 和 queue 的整体摘要。
- App Status overview：由 session、background jobs、read model readiness、dirty scopes、outbox、worker heartbeat、dependencies、alerts 推导 green/yellow/red。
- Dashboard 发票 inventory 只展示 `手工导入` 和 `OA 解析` 两类来源，不再展示 `普通导入` 或 `ETC`。统计事实源是统一发票池 `app.invoices.source_links`：`手工导入` 统计 `source_type='manual_invoice_import'` 的 active 发票，`OA 解析` 统计 `source_type='oa_attachment_invoice'` 的 active 发票，`OA 解析` 括号内数量统计带 OA 来源但不带手工导入来源的 active 发票。
- Dashboard 导入历史展示流水、手工发票、OA 解析和 OA 单据同步的每次导入数量；主页面只显示最新 5 条，右侧抽屉展示所有历史记录。

## 运行事实源

- PostgreSQL durable queue：`job.outbox_events`、`job.read_model_dirty_scopes`。
- Runtime monitoring：`RuntimeMonitoringRepository.app_status_runtime_snapshot()`、`health_summary()` 和 `ready_health_summary()`。这些查询必须使用同一 current-effective 口径过滤已被后续 `done` 或 fresh readiness 覆盖的历史 outbox/dirty scope；ready summary 查询失败必须暴露为 runtime unavailable，不能被空 payload 解释成绿色。
- Readiness：`read_model.app_status_readiness` 或 Workbench active generation 等价 readiness。
- Worker registry：`runtime_worker_registry.py`。
- Domain/read model/job/dependency registries：`app_status_*_registry.py`。
- 发票 inventory：读取 `app.invoices.source_links`，只统计已进入统一发票池且未删除的 canonical invoice facts；OA 附件 OCR cache 只作为解析缓存，不作为 App Health 发票 inventory 事实源。
- 导入历史：读取 `app.import_batches` 的银行流水/发票导入成功数、`app.invoices.source_links` 中 OA 附件发票 source link 的创建时间和补充数，以及 `app.oa_sync_runs(sync_type='oa_projection')` 的 OA 单据同步数。
- 前端只展示后端事实；不能用当前 route、表格 loading、组件本地状态推导全局状态。

## 关键 fan-out

| 来源 | App Health / Status 影响 | 受影响体验 |
| --- | --- | --- |
| read model missing/stale/refreshing | domain busy/yellow，暴露 scope diagnostics | 对应页面显示刷新中，App Status hover 可定位 |
| critical read model failed/unavailable | domain blocked/red，暴露 current-effective scope diagnostics | 对应页面不能假装 fresh；普通 read model failure 不进入全局写闸门，写入是否禁用由 `overall.write_safety` 和具体写 API precondition 决定 |
| required worker missing/stale/mismatch | domain blocked/red 或 busy/yellow | 所有依赖该 worker 的页面不能假设会收敛 |
| dirty scope/outbox backlog | domain busy/yellow；只统计当前有效记录，已被后续 `done` 或 `fresh` readiness 覆盖的旧 pending/failed 不再进入 backlog/同步中 | 用户看到真实后台刷新，而不是被历史队列噪声误导 |
| runtime summary counts | `/api/app-health.app_status.runtime_summary` 聚合 read model、worker、queue 状态 | 左上角 popover 和 `/operations/app-health` 必须能直接看出 fresh/refreshing/failed、active/working/stale/missing、pending/processing/failed/backlog |
| background job queued/running/attention | overall/domain busy 或 attention | 导入、数据重置、ETC、worker rebuild 状态可见 |
| dependency unavailable | blocked/red 或 degraded | OA/session/PostgreSQL/RabbitMQ/Redis 等依赖异常可见；operations dashboard 默认只把 RabbitMQ queue metrics 标记 unknown，不让可选管理接口拖慢写后健康探针 |
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
- `e2e-spec.md`：维护系统状态页 Spec-first Browser 业务验收合同。
- `e2e-coverage.md`：维护系统状态页 Spec-first 合同到自动化覆盖的映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
