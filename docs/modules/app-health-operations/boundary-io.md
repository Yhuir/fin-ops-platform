# 系统状态模块边界与 I/O

日期：2026-07-10

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：系统状态页面聚合 app health、app status、runtime worker/read model readiness；受控运维动作只能通过明确 admin-only endpoint 入队 runtime job，不直接改业务事实或 read model 表。
- 当前缺口：server.py 仍保留部分 app health/status endpoint。
- 旧代码删除条件：所有 health/status endpoint 有明确 route/service owner 且前端只读观测 API。

## 职责边界

### 负责

- 系统状态页面、健康告警、read model/worker readiness 展示。
- 聚合 app status domain/read model/job/dependency registry。
- 为运维判断 fresh/drain/worker 状态提供只读入口。

### 不负责

- 不直接修改业务事实、relation 或 read model 表。
- 不绕过 durable runtime queue 直接刷新 read model。
- 不隐藏 stale/refreshing 状态。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面读取 | `AppHealthOperationsPage.tsx`、`features/appHealth/api.ts` | 只读 API |
| Health probe | app health endpoints | 返回 readiness/status |
| Runtime registry | app status services | 聚合 worker/read model/job/dependency 状态；operations dashboard 默认不等待 RabbitMQ management API，RabbitMQ queue metrics 作为可选 transport 观测以 unknown 降级 |
| Dashboard inventory facts | `app.bank_transactions`、`app.invoices` / `source_links`、`app.import_batches`、`app.oa_*`、`app.oa_sync_runs` | 发票 inventory 按 canonical invoice source link 和 `invoice_type` 统计；OA 上次读取时间优先使用 `app.oa_sync_runs(sync_type='oa_projection')` 的成功 run；导入历史只读 `app.import_batches` 中手工银行流水和发票导入批次 |
| OA sync runtime facts | `job.outbox_events(event_type='oa.sync')`、`runtime_worker_heartbeats`、`app.oa_sync_runs` | `/api/oa-sync/status` 和 AppHealth `oa_sync` 只读 durable queue、worker 和 projection run facts；不得依赖 HTTP 进程内内存状态 |
| 进项使用全量审计 | `app.invoices`、`app.workbench_pair_relations`、`read_model.input_invoice_usage_*`、`read_model.workbench_relation_*`、`job.read_model_dirty_scopes` | `/api/operations/app-health/input-invoice-usage-audit` admin-only 只读；检查页面 read model、canonical 进项发票和 Workbench relation 分发是否一致；不得刷新、修复或写入 |
| 销项收款全量审计 | `app.invoices`、`app.workbench_pair_relations`、`read_model.output_invoice_collection_*`、`read_model.workbench_relation_*`、`job.read_model_dirty_scopes` | `/api/operations/app-health/output-invoice-collection-audit` admin-only 只读；检查页面 read model、canonical 销项发票和 Workbench relation 分发是否一致；不得刷新、修复或写入 |
| 进项使用受控刷新 | admin request body `scope_keys` | `/api/operations/app-health/input-invoice-usage-refresh` admin-only；只允许 `all` 或 `YYYY-MM` scope，通过 `ReadModelRefreshGateway` 入队 `input_invoice_usage.read_model.refresh`，不直接写 `read_model.input_invoice_usage_*` 或 relation |
| 销项收款受控刷新 | admin request body `scope_keys` | `/api/operations/app-health/output-invoice-collection-refresh` admin-only；只允许 `all` 或 `YYYY-MM` scope，通过 `ReadModelRefreshGateway` 入队 `output_invoice_collection.read_model.refresh`，不直接写 `read_model.output_invoice_collection_*` 或 relation |
| 待找发票受控刷新 | admin request body `scope_keys` | `/api/operations/app-health/pending-invoice-refresh` admin-only；只允许 `direction:filter_group[:YYYY-MM]` scope，通过 `ReadModelRefreshGateway` 入队 `pending_invoice.read_model.refresh`，不直接写 `read_model.pending_invoice_*` 或 relation |
| 页面业务全量审计 | `PAGE_AUDIT_CONTRACTS` 登记的 `app.*`、`read_model.*`、`job.*` source/read model/relation tables | `/api/operations/app-health/page-audit?domain=<domain_key>` admin-only 只读；待找发票、外部往来款管理、批量账务、流水规则批量处理、OA 待付款核对、银行明细、成本统计页面标题 Audit icon 使用该入口检查 App 内部 canonical expected-set、关键展示字段重算、read model rows/scopes/source_versions、durable refresh state，以及 canonical relation / relation groups / relation rows 的受影响月份双向 edge equality；所有 SQL 必须在同一 `REPEATABLE READ READ ONLY` 数据库快照中执行；`job.read_model_dirty_scopes` 与 `job.outbox_events` 必须按当前 OA session tenant 过滤；不得刷新、修复或写入 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| App health payload | 页面/indicator | 不伪装 readiness；OA pending/processing outbox 必须显示 refreshing，OA failed outbox/worker/run 必须显示 blocked/error |
| Alert/status | shell/status page | 明确 stale/failed/degraded |
| Dashboard payload | operations page | 只读聚合；`data_inventory.invoice.sources` 固定为 `manual`、`input_invoice`、`output_invoice`、`oa_attachment`，`input_invoice` / `output_invoice` 按 active canonical 发票的 `invoice_type` 统计，`oa_attachment.supplementary_count` 表示 OA 解析进入发票池但不在手工导入中的数量；`data_inventory.oa.sources` 包含 `oa_records`、`oa_records_completed`、`oa_records_in_progress`、`oa_items`，分别表示 OA 申请主表总数、已完成 OA、进行中 OA 和 OA 明细行数；`oa_records_completed` 统计 `app.oa_applications` 的唯一完成态 OA 单据，`oa_records_in_progress` 统计 OA 待付款 read model all-scope 的 `viewCounts.in_progress` 等价唯一 OA ID，不能用 `app.oa_applications.workflow_status` 推导；`data_inventory.oa.latest_synced_at` 使用最近成功 OA projection run；`data_inventory.import_events` 只输出手工银行流水和发票导入历史，前端主页面截取最新 5 条并用抽屉展示全量；RabbitMQ 管理指标默认以 unknown 输出，不能阻塞 read model/worker 健康探针 |
| 进项使用审计报告 | admin/API consumer | `overall_status=pass`、`audit_status.integrity=pass` 且 `audit_status.freshness=fresh` 才能证明已登记 invariant 一致；`*_sample_count` 是有上限样本，不是全量问题总数 |
| 销项收款审计报告 | admin/API consumer | `overall_status=pass`、`audit_status.integrity=pass` 且 `audit_status.freshness=fresh` 才能证明已登记 invariant 一致；`issues_found` 只报告有上限样本，不做自动修复 |
| 页面业务审计报告 | 页面标题 Audit icon / admin API consumer | `audit_status.integrity=pass`、`freshness=fresh`、`queue=drained` 且 `audit_contract.database_snapshot=true` 才能证明该页面“已登记的 App 内部合同”在同一快照内 canonical expected-set、关键展示字段、read model 和 relation 投影一致；`audit_contract` 必须列出 expected-set、关键字段、proof checks、snapshot consistency 与 external source boundary；不能证明外部银行/OA 系统本身没有漏同步 |
| 进项使用刷新入队结果 | runtime queue / admin caller | 返回 `202`、规范化 scope 列表和 enqueue count；完成与否必须继续通过 App Health、operation barrier 或审计 API 复核 |
| 销项收款刷新入队结果 | runtime queue / admin caller | 返回 `202`、规范化 scope 列表和 enqueue count；完成与否必须继续通过 App Health、operation barrier 或审计 API 复核 |
| 待找发票刷新入队结果 | runtime queue / admin caller | 返回 `202`、规范化 scope 列表和 enqueue count；完成与否必须继续通过 App Health、operation barrier 或审计 API 复核 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- Reads readiness of：all app status/read model/job registries。
- Reads facts of：`app.bank_transactions`、`app.invoices`、`app.import_batches`、`app.oa_applications`、`app.oa_application_items`、`app.oa_sync_runs`、`job.outbox_events`、`job.runtime_worker_heartbeats`。
- Service owner：`AppHealthService`、`AppStatusOverviewService`、`RuntimeMonitoring`。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/AppHealthOperationsPage.tsx` |
| Frontend feature/context | `web/src/features/appHealth/*`、`features/appStatus/*`、`contexts/AppHealthStatusContext.tsx` |
| Shell | `web/src/components/shell/AppStatusIndicator.tsx` |
| Backend route | `/api/app-health*`、`/api/operations/app-health-dashboard`、`/api/operations/app-health/input-invoice-usage-audit`、`/api/operations/app-health/output-invoice-collection-audit`、`/api/operations/app-health/page-audit`、`/api/operations/app-health/input-invoice-usage-refresh`、`/api/operations/app-health/output-invoice-collection-refresh`、`/api/operations/app-health/pending-invoice-refresh` in `server.py` |
| Backend service | `app_health_service.py`、`app_health_alert_service.py`、`app_status_overview_service.py`、`runtime_monitoring.py`、`operations_audit_service.py` |
| Backend audit repository | `services/postgres_repositories/operations_audit.py`、`audit_report.py`、`workbench_relation_audit.py`、`invoice_read_model_audit.py`、方向薄适配 `input_invoice_usage_audit.py` / `output_invoice_collection_audit.py`、`page_business_audit.py` |
| Registries | `app_status_domain_registry.py`、`app_status_read_model_registry.py`、`app_status_job_registry.py`、`app_status_dependency_registry.py` |
| Tools/tests | `tools/app_status_readiness_backfill.py`、`tools/audit_input_invoice_usage_read_model.py`、`tools/audit_output_invoice_collection_read_model.py`、`tools/audit_page_business_read_model.py`、`tests/test_app_health*.py`、`tests/test_app_status*.py`、`tests/test_audit_input_invoice_usage_read_model_tool.py`、`tests/test_audit_output_invoice_collection_read_model_tool.py`、`tests/test_audit_page_business_read_model_tool.py` |

## 依赖方向

- 允许依赖：status registries, runtime monitoring, app health services。
- 必须通过：`server.py -> OperationsAuditService -> PostgresOperationsAuditRepository`；进/销项共同 invariant 由 `InvoiceReadModelAuditContract` 驱动单一 core，方向文件只选 contract；`tools/audit_*.py` 只允许命令行参数与输出适配。
- 禁止绕过：系统状态页面直接改业务/read model 表；隐藏 failed/stale worker；用行级 projection `synced_at` 或内存状态覆盖 durable OA sync run/outbox/worker facts。

## 测试与验证

- `tests/test_app_health_api.py`
- `tests/test_app_health_service.py`
- `tests/test_app_status_overview_service.py`
- `tests/test_operations_dashboard_service.py`
- `tests/test_audit_input_invoice_usage_read_model_tool.py`
- `tests/test_audit_output_invoice_collection_read_model_tool.py`
- `tests/test_audit_page_business_read_model_tool.py`
- `tests/test_operations_audit_service.py`
- `tests/test_operations_audit_report.py`
- `web/src/test/AppHealthOperationsPage.test.tsx`
- `web/src/test/PageAuditIcon.test.tsx`

## 当前缺口和删除条件

- 如果引入直接修复操作，必须拆成独立运维 command 模块并补权限/审计；只入队 read model refresh 的操作必须保持 admin-only、scope policy 校验和 runtime queue 边界。
