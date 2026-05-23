# AppHealth 运维状态只读 Dashboard 设计

## 背景

当前 `AppHealthOperationsPage` 偏向故障处理和后台任务操作，页面包含 Summary、Session、OA Sync、Workbench Read Model、Background Jobs、Dependencies、Alerts，以及 retry/acknowledge 操作。新的需求是把该页面重构为只读生产观测 Dashboard：

- 显示导入数据盘点：流水、发票、OA。
- 显示实时 p95/p99：API、数据库拆解、后台链路。
- 移除现有运维操作和旧内容。
- UI 简洁，参考 HeroUI 风格，但不引入 HeroUI 依赖，继续使用现有 MUI。

## 目标

新增独立只读接口和页面视图，让管理员进入 `AppHealth 运维状态` 时可以快速判断：

1. 数据进来了多少。
2. 当前用户请求是否变慢。
3. 后台 outbox、RabbitMQ、worker、read model 链路是否堵塞。

## 非目标

- 不新增时序库、Prometheus、Grafana 或长期趋势存储。
- 不做 retry、acknowledge、requeue、republish 等运维操作。
- 不展示原始业务 payload、数据库 URL、RabbitMQ URL、OA token、对象存储 secret。
- 不引入 HeroUI 包。
- 不把 unknown 指标显示成 `0`。

## 后端接口

新增只读接口：

```text
GET /api/operations/app-health-dashboard
```

权限：

- 仅 admin 可访问。
- 复用现有 OA session 和 app 权限体系。
- 非 admin 返回 `403`。
- 未登录或登录态失效返回现有 `401` 语义。

该接口独立于现有 `/api/app-health`。现有 `/api/app-health` 继续服务全局健康状态、侧边栏、工作台 mutation gating 和 SSE 订阅，避免 Dashboard 重构影响全局健康判断。

### 响应结构

```ts
type OperationsDashboardPayload = {
  generated_at: string;
  data_inventory: {
    bank: DataInventoryBlock;
    invoice: InvoiceInventoryBlock;
    oa: OaInventoryBlock;
  };
  request_performance: {
    window: {
      type: "process_rolling_window";
      sample_limit_per_endpoint: number;
      reset_on_restart: true;
    };
    endpoints: EndpointPerformance[];
  };
  runtime_performance: {
    outbox: OutboxMetric;
    queues: QueueRuntimeMetric[];
    read_models: ReadModelRuntimeMetric[];
    workers: WorkerRuntimeMetric[];
  };
  freshness: {
    warnings: string[];
  };
};
```

不要返回页面不需要的 `status` 总览字段。页面只展示字段和数字，不展示 `正常 / 降级 / 异常 / 采样不足` 这类总览文案。

## 数据盘点口径

数据盘点分三块：流水、发票、OA。

### 流水

```ts
bank: {
  total_count: number | null;
  latest_synced_at: string | null;
  status: "available" | "unknown";
  sources: [
    {
      key: "bank_transactions";
      label: "银行流水";
      count: number | null;
      latest_synced_at: string | null;
      status: "available" | "unknown";
    }
  ];
}
```

口径：

- `total_count`：`app.bank_transactions` 行数，排除逻辑删除状态时沿用现有业务状态约定；当前 schema 没有统一 deleted 字段时按全量行数。
- `latest_synced_at`：优先取关联 `app.import_batches.imported_at` 的最大值；没有关联批次时退回 `app.bank_transactions.updated_at` 最大值。
- 查询必须基于 PostgreSQL 表聚合，不从旧 snapshot 或前端数据推断。

### 发票

```ts
invoice: {
  total_count: number | null;
  latest_synced_at: string | null;
  status: "available" | "unknown";
  sources: [
    { key: "standard_import"; label: "普通导入"; count: number | null; latest_synced_at: string | null; status: "available" | "unknown" },
    { key: "oa_attachment"; label: "OA 解析"; count: number | null; latest_synced_at: string | null; status: "available" | "unknown" },
    { key: "etc"; label: "ETC"; count: number | null; latest_synced_at: string | null; status: "available" | "unknown" },
    { key: "manual"; label: "手工导入"; count: number | null; latest_synced_at: string | null; status: "available" | "unknown" }
  ];
}
```

口径：

- `total_count`：发票总量。
- `standard_import`：`app.invoices` 中 `status <> 'deleted'`，并且不是 manual、ETC、OA attachment 的发票。当前 schema 没有 `source_kind`，实现必须使用下面的判定顺序。
- `manual`：沿用现有 `_workbench_invoice_inventory()` 的 `source_links` 判定：`source_links[*].source_type/type/source = 'manual_invoice_import'`。
- `etc`：沿用现有 `_workbench_invoice_inventory()` 的 ETC 判定：`etc_invoice_id` 非空，或 `source_links` 中有 `etc_import` / `etc_invoice_import` / `etc_submission`，或 `tags && array['ETC','etc','etc_invoice']`。
- `oa_attachment`：优先使用 `read_model.workbench_rows` 中 `source_kind = 'oa_attachment_invoice'` 的 `distinct row_id` 数量；如果 read model 不可用，退回 `app.oa_attachment_invoice_cache` 中解析出的发票数量；如果两者都无法可靠统计，返回 `count: null`、`status: "unknown"`，并写入 warning code `invoice_oa_attachment_inventory_unknown`。
- `latest_synced_at`：优先取各来源自己的最新时间后汇总最大值：普通/手工/ETC 发票使用 `app.import_batches.imported_at` 或 `app.invoices.updated_at`；OA 解析使用 `app.oa_attachment_invoice_cache.parsed_at`；没有可靠来源时为 `null`。
- 如果某个来源当前没有可靠字段区分，返回 `count: null` 和 `status: "unknown"`，不得显示为 `0`。

### OA

```ts
oa: {
  total_count: number | null;
  latest_synced_at: string | null;
  status: "available" | "unknown";
  sources: [
    { key: "oa_records"; label: "单据"; count: number | null; latest_synced_at: string | null; status: "available" | "unknown" },
    { key: "oa_items"; label: "明细"; count: number | null; latest_synced_at: string | null; status: "available" | "unknown" }
  ];
}
```

口径：

- `oa_records`：`app.oa_applications` 行数。
- `oa_items`：`app.oa_application_items` 行数。
- `latest_synced_at`：优先取 `app.oa_applications.synced_at` 最大值；没有应用行时取 `app.oa_sync_watermarks.last_success_at` 最大值；仍没有则取成功 `app.oa_sync_runs.finished_at` 最大值。

## 请求性能口径

请求性能来自现有进程内 rolling window，不接时序库。

```ts
type EndpointPerformance = {
  endpoint: string;
  sample_count: number;
  last_status_code: number | null;
  duration_ms: Percentiles;
  database_duration_ms: Percentiles;
  connection_acquire_ms: Percentiles;
  sql_execute_fetch_ms: Percentiles;
  database_query_count: Percentiles;
};

type Percentiles = {
  p50: number | null;
  p95: number | null;
  p99: number | null;
};
```

默认展示这些 endpoint：

- `GET /api/workbench/summary`
- `GET /api/workbench/groups`
- `GET /api/search`
- `GET /api/pending-invoices/rows`
- `GET /api/cost-statistics`
- `GET /api/cost-statistics/explorer`
- `GET /api/tax-offset`
- `GET /api/app-health`
- `GET /api/operations/app-health-dashboard`

排序：

1. p95 高的排前。
2. p95 为空但有错误状态码的排前。
3. 其他按 endpoint 名称稳定排序。

前端不显示 `ok/warn/critical` 文案，只用颜色强调慢值。

建议颜色阈值：

- API p95 `< 500ms`：默认。
- API p95 `500ms - 1500ms`：amber。
- API p95 `> 1500ms`：red。
- API p99 `> 2500ms`：amber。
- API p99 `> 5000ms`：red。
- 样本或数值为 `null`：显示 `--`。

## 后台链路口径

后台链路来自 PostgreSQL outbox、runtime worker heartbeat、read model refresh 指标和 RabbitMQ 管理接口。

```ts
type OutboxMetric = {
  pending_count: number | null;
  publishing_count: number | null;
  failed_count: number | null;
  publish_failed_count: number | null;
  oldest_pending_age_seconds: number | null;
  status: "available" | "unknown";
  warning_code?: string;
};

type QueueRuntimeMetric = {
  event_type: string;
  queue: string;
  messages: number | null;
  unacked: number | null;
  consumers: number | null;
  dlq_messages: number | null;
  status: "available" | "unknown";
  warning_code?: string;
};

type ReadModelRuntimeMetric = {
  key: string;
  refresh_duration_ms: Percentiles;
  stale_count: number | null;
  unavailable_count: number | null;
  status: "available" | "unknown";
  warning_code?: string;
};

type WorkerRuntimeMetric = {
  worker_kind: string;
  heartbeat_lag_seconds: number | null;
  status: "available" | "unknown";
  warning_code?: string;
};
```

实现必须扩展 `RuntimeMonitoringRepository` 或新增运维 dashboard 专用 repository 方法，返回页面需要的行级指标，而不是让前端从旧聚合字段猜测：

- `queues`：基于 `rabbitmq_event_routes(RuntimeQueueSettings.from_env())` 的 event type 到 queue/DLQ 映射，并从 RabbitMQ Management API 的 per-queue summary 读取 `messages`、`messages_unacknowledged`、`consumers` 和 DLQ messages。RabbitMQ 管理接口不可用时，所有 queue 行仍按已知 route 输出，数值为 `null`，`status: "unknown"`，warning code 为 `rabbitmq_metrics_unavailable`。
- `workers`：从 `job.runtime_worker_heartbeats` 按 worker kind 或 worker id 输出 heartbeat lag。无法区分 worker kind 时输出 worker id，并保持字段名 `worker_kind`。
- `read_models`：至少输出 `workbench`、`search`、`pending_invoice`、`cost_statistics`、`tax_offset`。refresh duration 来自 `job.outbox_events.raw_payload.runtime_result.duration_ms`，按 event type 分组计算 p50/p95/p99；stale/unavailable 计数来自已有 read model status metric 能力或 outbox/read model dirty scope 状态。无法可靠拆分时该 read model 行返回 `status: "unknown"` 和 warning code，不合并成一个总数冒充分项。
- `outbox`：从 `job.outbox_events` 聚合 status 和 publish_status，`oldest_pending_age_seconds` 使用 pending event 的最大 age。

前端展示分三组：

- `Outbox`
- `RabbitMQ`
- `Worker / Read Model`

页面只显示数据，不提供操作按钮。

## 错误和降级策略

`/api/operations/app-health-dashboard` 不应因为某一个统计来源失败导致整页 500。

规则：

- 权限失败继续返回 `401/403`。
- 某个指标来源失败时，该区块返回完整结构，但对应值为 `null`，`status` 为 `unknown`，并记录短码到 `freshness.warnings`。
- 服务端日志记录具体异常。
- 前端只显示 `未知` 或 `--`，不展示长错误堆栈。
- 刷新失败时保留上一份数据，顶部只显示 `刷新失败`。

## 页面设计

页面标题：

```text
AppHealth 运维状态
```

顶部仅保留：

- 标题。
- 小型刷新按钮或图标。
- 次级更新时间，例如 `更新 00:31:20`。

不显示副标题，不显示总览状态，不显示解释性长文案。

### 页面区块

1. 数据盘点
   - 流水
   - 发票
   - OA
2. 请求性能
   - endpoint 表格。
3. 后台链路
   - Outbox
   - RabbitMQ
   - Worker / Read Model

### 文案约束

字段名保持短：

- `总数`
- `最近同步`
- `普通导入`
- `OA 解析`
- `ETC`
- `手工导入`
- `单据`
- `明细`
- `接口`
- `样本`
- `状态码`
- `总耗时 p95`
- `总耗时 p99`
- `DB p95`
- `DB p99`
- `SQL p95`
- `SQL p99`
- `连接 p95`
- `连接 p99`
- `查询数 p95`
- `pending`
- `publishing`
- `failed`
- `oldest`
- `queue`
- `messages`
- `unacked`
- `consumers`
- `DLQ`
- `worker`
- `lag`
- `refresh p95`
- `refresh p99`
- `stale`
- `unavailable`

空状态：

- `加载失败`
- `刷新失败`
- `暂无数据`
- `未知`
- `--`

## UI 实现方式

不新增 HeroUI 依赖。使用现有 MUI 做 HeroUI 风格：

- 白底或极浅灰背景。
- 8px 以内圆角。
- 轻边框，少阴影。
- 数字使用 tabular nums。
- 表格紧凑，适合运维扫描。
- 慢值用轻微色彩强调，不显示状态文案。
- 不使用大面积渐变、装饰图形或 marketing hero。
- 不嵌套卡片。

建议组件：

- `MetricCard`
- `MetricRow`
- `PerformanceTable`
- `RuntimeTable`
- `CompactTimestamp`
- `MutedEmpty`
- `SeverityNumber`

MUI 组件：

- `Box`
- `Stack`
- `Typography`
- `Button`
- `Chip`
- `Table`
- `TableContainer`
- `TableHead`
- `TableBody`
- `TableRow`
- `TableCell`
- `Alert`
- `CircularProgress`

不用 `DataGrid`，除非实现过程中发现表格行数明显超出普通 Table 的可维护范围。

## 刷新策略

- 首次进入立即加载。
- 默认每 10 秒刷新一次。
- 手动刷新按钮触发立即刷新。
- 请求中显示 loading。
- 离开页面 abort 当前请求。
- 如果上一轮请求未完成，不启动新的并发刷新。
- 刷新失败保留旧数据。

## 测试策略

本功能同时更新长期文档：

- `docs/product-specs/app-health-and-background-jobs.md`：记录 AppHealth 运维状态页的新只读定位、数据盘点口径和不再承载后台任务操作。
- `docs/dev/api-contracts.md`：记录 `GET /api/operations/app-health-dashboard` 响应 contract。
- `docs/operations/monitoring.md`：记录 dashboard 指标来源、rolling window 限制、RabbitMQ/outbox/read model 展示口径。

后端测试：

- admin 可访问 dashboard。
- 非 admin 返回 `403`。
- 数据盘点返回 bank、invoice、oa。
- invoice sources 包含 `standard_import`、`oa_attachment`、`etc`、`manual`。
- 某个统计来源失败时整页仍返回 `200`，失败区块为 unknown/null。
- API performance 返回 p95/p99。
- runtime performance 返回 outbox、queue、worker、read model。
- 响应不包含 secret 字段。

前端测试：

- 无 admin 权限显示权限提示。
- 成功加载显示流水、发票、OA 三块。
- 请求性能显示 p95/p99。
- 后台链路显示 Outbox、RabbitMQ、Worker / Read Model。
- 手动刷新会重新请求。
- 刷新失败时保留旧数据并显示 `刷新失败`。
- unknown/null 不显示成 0。
- 页面不再渲染旧内容：
  - Summary
  - Session
  - Background Jobs
  - Dependencies
  - Alerts
  - Retry
  - Acknowledge

验收命令：

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_operations_dashboard_service \
  tests.test_app_health_api \
  tests.test_runtime_monitoring \
  -v
npm test -- --run src/test/AppHealthOperationsPage.test.tsx
npm run build
git diff --check
```

## Spec Review

- Review status: approved after updating invoice source contracts, runtime metric row contracts, unknown/null semantics, documentation acceptance criteria, and repository verification commands.

## 最终执行 Prompt

```text
/goal 生产级重构 AppHealth 运维状态为只读 Dashboard：新增独立 GET /api/operations/app-health-dashboard 接口，展示流水/发票/OA 数据盘点、当前进程 rolling window 的 API/DB p95/p99、PostgreSQL outbox/RabbitMQ/worker/read model 后台链路指标；移除现有 AppHealth 运维页所有旧内容和操作按钮；使用现有 MUI 实现 HeroUI 风格的简洁只读 UI，不新增 HeroUI 依赖。

执行要求：
1. 阅读 AGENTS.md、docs/product-specs/app-health-and-background-jobs.md、docs/operations/monitoring.md、现有 AppHealthOperationsPage、appHealth API/types、AppHealthService、ApiPerformanceRecorder、RuntimeMonitoringRepository。
2. 不改动现有 /api/app-health 的全局健康判断职责；新增 /api/operations/app-health-dashboard 作为运维页专用只读接口。
3. 后端新增聚合服务，避免继续膨胀 server.py；handler 只做鉴权、调用 service、返回 JSON。
4. 数据盘点分 bank/invoice/oa；invoice sources 必须包含 standard_import、oa_attachment、etc、manual；unknown 不能显示为 0。
5. 请求性能展示 duration/database/sql/connection/query_count 的 p95/p99，来自当前进程 rolling window。
6. 后台链路展示 outbox、RabbitMQ queues/DLQ、worker heartbeat lag、read model refresh p95/p99/stale/unavailable。
7. UI 文案保持简洁：无副标题、无总览状态、无解释性长文案；顶部只保留标题、刷新按钮、更新时间。
8. 移除旧页面内容：Summary、Session、OA Sync、Workbench Read Model、Background Jobs、Dependencies、Alerts、Retry、Acknowledge。
9. 页面只读；不提供 retry、acknowledge、requeue、republish 等操作。
10. 生产级错误边界：单个指标来源失败不让整页 500；该区块显示未知/null，并记录短码 warning；权限失败仍 401/403。
11. 添加后端和前端回归测试，覆盖权限、数据口径、p95/p99、runtime 指标、unknown/null、刷新失败保留旧数据、旧内容消失。
12. 同步更新 docs/product-specs/app-health-and-background-jobs.md、docs/dev/api-contracts.md、docs/operations/monitoring.md。
13. 运行后端相关 unittest、前端相关 vitest、npm run build、git diff --check。
```
