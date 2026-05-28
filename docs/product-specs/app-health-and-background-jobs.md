# 健康状态与后台任务

## 目标

App Health 状态栏和后台任务体系用于暴露 OA 同步、工作台 read model、成本统计预热、ETC 修复、数据重置等长期运行任务的状态。

设置页的 `AppHealth 运维状态` 是只读观测 Dashboard。它不承载 retry、acknowledge、requeue、republish 或数据修复动作，只帮助管理员快速判断数据、请求性能和后台链路是否正常。

## 后台任务要求

任务必须有：

- `job_id`。
- 类型和来源。
- 当前状态。
- 阶段。
- 当前进度和总量。
- 百分比。
- 创建时间和更新时间。
- 结果或失败原因。
- 可重试或不可重试标记。

## 健康状态

健康状态应覆盖：

- OA 连接和同步状态。
- 工作台匹配 dirty scopes。
- 工作台 read model 刷新状态，包括 `fresh`、`refreshing`、`stale`、`failed`、`unavailable`、worker lag、最近错误和可重试性。
- 工作台状态必须暴露 `active_generation_id`、`building_generation_id`、`failed_generation_id` 和 `read_model_version`。`read_model_version` 优先等于 active generation，用于前端判断是否需要无刷新重读当前分页窗口。
- 成本统计缓存预热。
- 后台任务失败或需关注项。
- Mongo/app state 连接状态。

`/api/app-health` 继续作为全局健康状态事实源，供状态栏、侧边栏、多标签页同步和写操作 gating 使用。不要把该接口改造成运维 Dashboard，也不要让 Dashboard 重构影响全局健康判断。

关联工作台页面还可以订阅 `GET /api/workbench/events?month=all`。该 SSE 流只服务页面级刷新体验：它推送 read model 状态和版本变化，前端据此自动重读当前分页窗口；全局阻塞判断仍以 `/api/app-health` 为准。SSE 不可用时，页面回退轮询 `/api/workbench/refresh-status`，并在窗口重新获得焦点时补偿检查一次。

## AppHealth 运维状态 Dashboard

Dashboard 读取 `GET /api/operations/app-health-dashboard`，仅管理员可访问。

页面展示三组只读数据：

- `数据`：流水、发票、OA 的总量和最近同步时间。发票来源拆为普通导入、OA 解析、ETC、手工导入。
- `请求`：当前 API 进程 rolling window 的请求耗时和数据库拆解 p95/p99。
- `后台`：PostgreSQL outbox、RabbitMQ queue/DLQ、worker heartbeat、read model refresh/stale 指标。

数据口径：

- 流水来自 `app.bank_transactions`，最近同步时间优先使用关联 `app.import_batches.imported_at`。
- 发票总量来自 `app.invoices` 且排除 `status='deleted'`。ETC 和手工导入沿用 `source_links`、`etc_invoice_id`、`tags` 的现有判定。OA 解析优先读 `read_model.workbench_rows.source_kind='oa_attachment_invoice'`，不可用时退回 `app.oa_attachment_invoice_cache`。
- OA 单据和明细来自 `app.oa_applications`、`app.oa_application_items`。
- unknown 指标必须返回 `null` 和 `status='unknown'`，前端显示 `--`，不得显示成 `0`。

## 验收标准

- 页面不因长任务阻塞。
- 关联工作台刷新期间保留最近稳定数据，不出现空白页，不要求用户手动刷新。
- worker lag 持续高于告警阈值、存在 failed generation、或 dirty scope 长时间停留在 `pending/processing` 时，App Health 必须提示刷新异常；页面继续读取最近 active generation，避免半成品数据进入用户视图。
- 全局健康状态中的失败任务能被用户识别和重试。
- AppHealth 运维状态页不出现 retry、acknowledge 或其它写操作。
- Dashboard 能展示流水、发票、OA 数量和最近同步时间。
- Dashboard 能展示 API/DB p95/p99、outbox、RabbitMQ、worker、read model 指标。
- 需要管理员处理的状态明确提示。
- 多标签页状态同步不重复广播过旧状态。
