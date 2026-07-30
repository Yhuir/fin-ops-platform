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
- `backend/src/fin_ops_platform/app/server.py` 中 `/api/app-health*`、`/api/operations/app-health-dashboard`、`/api/operations/app-health/page-audit`
- `backend/src/fin_ops_platform/services/app_health_service.py`
- `backend/src/fin_ops_platform/services/app_health_alert_service.py`
- `backend/src/fin_ops_platform/services/app_status_overview_service.py`
- `backend/src/fin_ops_platform/services/runtime_monitoring.py`
- `backend/src/fin_ops_platform/services/external_control_evidence.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/external_control_evidence.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/external_control_evidence_audit.py`
- `backend/src/fin_ops_platform/tools/external_control_evidence.py`
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
- `/api/operations/app-health/page-audit?page=<page_key>`：17 页统一 admin-only 只读 Audit。普通页面只执行 registry 选定的有限 proof owner；`page=app-health-operations` 是 system owner，在一个 outer `REPEATABLE READ READ ONLY` snapshot 内执行其余 16 页 proof、App Health dashboard database inventory 和 durable runtime/registry证明。该入口只输出 `pass/issues_found`，不刷新、不修复、不写业务数据。
- System Audit 返回 `database_system_snapshot`、`runtime_observation`、`external_evidence`。数据库面绑定 snapshot id、system audit id、17 页 revision、read model manifest 和 worker registry fingerprint；进程内 request metrics/RabbitMQ 仅为 point-in-time observation。外部面只读取已审计登记的银行/OA/发票/ETC `complete_snapshot/all` manifest，在同一 outer snapshot 内对 canonical item set、关键字段 fingerprint 和 controls 做精确双向 equality。四域全部通过才返回 `proven_as_of_external_evidence`；缺失为 unknown，撤销/过期/不一致为 fail，内部通过不能覆盖外部结论。
- 进项使用、销项收款和待找发票的旧 AppHealth refresh routes 已删除；调用返回 `404`，不得写 runtime queue。完整性证明只走统一只读 page audit。
- `/health` / `/health/ready`：公开或探针使用的轻量运行健康摘要；`api_performance.endpoints` 只保留 bounded 最慢 endpoint 摘要，完整 endpoint 明细由 `/metrics` 或 admin-only operations dashboard 提供。
- App Status icon/popover：全局状态入口，只消费后端 `app_status`，不读取当前页面局部 loading；popover 必须显示 read model、worker 和 queue 的整体摘要。
- App Status overview：由 session、background jobs、read model readiness、dirty scopes、outbox、worker heartbeat、dependencies、alerts 推导 green/yellow/red。
- Dashboard 发票 inventory 按两个互斥维度展示：`进项发票 + 销项发票 = 发票总数`，以及 `手工导入 + OA 解析仅新增入池 = 发票总数`。统计事实源是统一发票池 `app.invoices`：类型维度按 `invoice_type`；导入方式维度的手工导入统计 `source_links[].source_type='manual_invoice_import'`，OA 解析使用带 OA 来源但不带手工导入来源的 `oa_attachment.supplementary_count`，不能使用会与手工导入重叠的 OA 总关联数。已知数量不闭合时页面显示差异，不补造“其他”分类；未知数量显示 `--`。`普通导入`、`ETC` 和 OA 附件 OCR cache 不进入该展示口径。
- Dashboard OA 页面只展示 `已完成 OA` 和 `进行中 OA` 两个状态。API 仍保留 `oa_records` / `oa_items` 供 audit 和系统合同使用，但页面不展示“单据”“明细”或含义不同的 OA 总数；`已完成 OA` 按 canonical OA projection 完成态合同统计唯一 OA 单据，空/历史完成态别名归入已完成；`进行中 OA` 按 `app.oa_pending_payment_admissions` 的唯一 OA ID 统计，不读取已退役页面 projection，也不只按 `app.oa_applications.workflow_status` 推导。
- Dashboard 导入历史只展示手工导入的银行流水和发票批次；OA 解析和 OA 单据同步只属于发票/OA inventory 与运行状态，不进入最近导入记录。主页面只显示最新 5 条，右侧抽屉展示所有历史记录。

## 运行事实源

- PostgreSQL durable queue：`job.outbox_events`、`job.read_model_dirty_scopes`。
- Runtime monitoring：`RuntimeMonitoringRepository.app_status_runtime_snapshot()`、`health_summary()` 和 `ready_health_summary()`。这些查询必须使用同一 current-effective 口径过滤已被后续 `done` 或 fresh readiness 覆盖的历史 outbox/dirty scope；App Status summary 只读取状态推导实际消费的 readiness 列，不得解码未消费的逐 scope `source_versions`，完整版本证据由 Operations dashboard 的独立 scope-evidence I/O 负责；ready summary 查询失败必须暴露为 runtime unavailable，不能被空 payload 解释成绿色。
- Readiness：只覆盖 manifest 登记的关联台 active-generation `workbench` 与三个共享 read model（`workbench_relation`、`search`、`no_oa_bank_batch`），事实源是 `read_model.app_status_readiness` 和 current-effective durable queue；其它已退役页面没有 readiness。
- Worker registry：`runtime_worker_registry.py`。
- Domain/read model/job/dependency registries：`app_status_*_registry.py`。
- 发票 inventory：读取 `app.invoices.source_links`，只统计已进入统一发票池且未删除的 canonical invoice facts；OA 附件 OCR cache 只作为解析缓存，不作为 App Health 发票 inventory 事实源。
- 进项/销项页面审计：各页面只读 canonical facts 与 active canonical relations，不读取页面 consumer projection、`workbench_relation` 或 refresh queue；App Health 不再保留进项专项 Audit panel。
- 页面业务审计：只读 `PAGE_AUDIT_CONTRACTS` 登记的 canonical source/relation/job 表，不读取已退役页面 projection，也不 enqueue；`*_sample_count` 只是有上限的问题样本，不能把 50/100/150 当成精确问题总数。OA 待付款等依赖外部 OA/银行系统的页面仍需要外部 sync/runbook 证明来源系统本身完整。
- 导入历史：只读取 `app.import_batches` 的 `bank_transaction`、`input_invoice`、`output_invoice` 批次成功数。
- 前端只展示后端事实；不能用当前 route、表格 loading、组件本地状态推导全局状态。
- App Health System Audit 成功后用响应内同一 snapshot 的 `page_projection` 更新 dashboard；后续普通 dashboard refresh 会清除旧 Audit 状态，避免把历史快照继续显示为当前绿色。
- 外部 manifest 的 validate/register/revoke 仅通过运维 CLI 和独立 service/repository 边界执行；System Audit、页面 route 和 UI 都没有登记或修复能力。具体合同和授权门禁见 `docs/operations/external-control-evidence.md`。

## 关键 fan-out

| 来源 | App Health / Status 影响 | 受影响体验 |
| --- | --- | --- |
| retained read model missing/stale/refreshing | domain busy/yellow，暴露 scope diagnostics | 只影响 manifest 登记的共享消费者；直接读取页面继续按 canonical API 结果工作 |
| critical retained read model failed/unavailable | domain blocked/red，暴露 current-effective scope diagnostics | 共享消费者不能假装 fresh；故障不进入全局写闸门，写入是否禁用由 `overall.write_safety` 和具体写 API precondition 决定 |
| required worker missing/stale/mismatch | domain blocked/red 或 busy/yellow | 所有依赖该 worker 的页面不能假设会收敛 |
| dirty scope/outbox backlog | domain busy/yellow；只统计当前有效记录，已被后续 `done` 或 `fresh` readiness 覆盖的旧 pending/failed 不再进入 backlog/同步中 | 用户看到真实后台刷新，而不是被历史队列噪声误导 |
| runtime summary counts | `/api/app-health.app_status.runtime_summary` 聚合 read model、worker、queue 状态 | 左上角 popover 和 `/operations/app-health` 必须能直接看出 fresh/refreshing/failed、active/working/stale/missing、pending/processing/failed/backlog |
| background job queued/running/attention | overall/domain busy 或 attention | 导入、数据重置、ETC、worker rebuild 状态可见 |
| dependency unavailable | blocked/red 或 degraded | OA/session/PostgreSQL/RabbitMQ/Redis 等依赖异常可见；operations dashboard 默认只把 RabbitMQ queue metrics 标记 unknown，不让可选管理接口拖慢写后健康探针 |
| dashboard 整体构建失败 | dashboard 保留上一份 payload 并显示 stale warning | 运维读侧不中断，但不能作为 fresh 事实 |
| dashboard 局部指标失败 | 当前 payload 保留其它成功区块，失败区块显示 unknown/warning | inventory、导入历史等独立事实不得被旧缓存冻结 |

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
