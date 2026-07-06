# 系统状态模块边界与 I/O

日期：2026-07-03

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：系统状态页面只聚合 app health、app status、runtime worker/read model readiness，不承载业务修复逻辑。
- 当前缺口：server.py 仍保留部分 app health/status endpoint。
- 旧代码删除条件：所有 health/status endpoint 有明确 route/service owner 且前端只读观测 API。

## 职责边界

### 负责

- 系统状态页面、健康告警、read model/worker readiness 展示。
- 聚合 app status domain/read model/job/dependency registry。
- 为运维判断 fresh/drain/worker 状态提供只读入口。

### 不负责

- 不直接执行生产修复或数据写操作。
- 不直接刷新 read model。
- 不隐藏 stale/refreshing 状态。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面读取 | `AppHealthOperationsPage.tsx`、`features/appHealth/api.ts` | 只读 API |
| Health probe | app health endpoints | 返回 readiness/status |
| Runtime registry | app status services | 聚合 worker/read model/job/dependency 状态；operations dashboard 默认不等待 RabbitMQ management API，RabbitMQ queue metrics 作为可选 transport 观测以 unknown 降级 |
| Dashboard inventory facts | `app.bank_transactions`、`app.invoices.source_links`、`app.import_batches`、`app.oa_*`、`app.oa_sync_runs` | 发票来源只按 canonical invoice source link 统计；OA 上次读取时间优先使用 `app.oa_sync_runs(sync_type='oa_projection')` 的成功 run；导入历史只读 `app.import_batches` 中手工银行流水和发票导入批次 |
| OA sync runtime facts | `job.outbox_events(event_type='oa.sync')`、`runtime_worker_heartbeats`、`app.oa_sync_runs` | `/api/oa-sync/status` 和 AppHealth `oa_sync` 只读 durable queue、worker 和 projection run facts；不得依赖 HTTP 进程内内存状态 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| App health payload | 页面/indicator | 不伪装 readiness；OA pending/processing outbox 必须显示 refreshing，OA failed outbox/worker/run 必须显示 blocked/error |
| Alert/status | shell/status page | 明确 stale/failed/degraded |
| Dashboard payload | operations page | 只读聚合；`data_inventory.invoice.sources` 固定为 `manual`、`oa_attachment`，`oa_attachment.supplementary_count` 表示 OA 解析进入发票池但不在手工导入中的数量；`data_inventory.oa.sources` 包含 `oa_records`、`oa_records_completed`、`oa_records_in_progress`、`oa_items`，分别表示 OA 申请主表总数、已完成 OA、进行中 OA 和 OA 明细行数；`data_inventory.oa.latest_synced_at` 使用最近成功 OA projection run；`data_inventory.import_events` 只输出手工银行流水和发票导入历史，前端主页面截取最新 5 条并用抽屉展示全量；RabbitMQ 管理指标默认以 unknown 输出，不能阻塞 read model/worker 健康探针 |

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
| Backend route | `/api/app-health*`、`/api/operations/app-health-dashboard` in `server.py` |
| Backend service | `app_health_service.py`、`app_health_alert_service.py`、`app_status_overview_service.py`、`runtime_monitoring.py` |
| Registries | `app_status_domain_registry.py`、`app_status_read_model_registry.py`、`app_status_job_registry.py`、`app_status_dependency_registry.py` |
| Tools/tests | `tools/app_status_readiness_backfill.py`、`tests/test_app_health*.py`、`tests/test_app_status*.py` |

## 依赖方向

- 允许依赖：status registries, runtime monitoring, app health services。
- 必须通过：read-only service APIs。
- 禁止绕过：系统状态页面触发业务写操作；隐藏 failed/stale worker；用行级 projection `synced_at` 或内存状态覆盖 durable OA sync run/outbox/worker facts。

## 测试与验证

- `tests/test_app_health_api.py`
- `tests/test_app_health_service.py`
- `tests/test_app_status_overview_service.py`
- `tests/test_operations_dashboard_service.py`
- `web/src/test/AppHealthOperationsPage.test.tsx`

## 当前缺口和删除条件

- 如果引入修复操作，必须拆成独立运维 command 模块并补权限/审计。
