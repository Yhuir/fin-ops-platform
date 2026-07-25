---
phase: 28-cost-statistics-recovery-performance
plan: "01"
status: complete
completed_at: "2026-07-25T20:15:06+08:00"
commits:
  - d8e4c5946
  - b6e814b05
production_release: main-b6e814b0-20260725192427
---

# Phase 28 Plan 01 执行总结

## 结果

成本统计写后恢复热路径已完成生产闭环。相同 `2026-02` exact-scope 样本从
`7432.418 ms` 降到 `723.151 ms`，改善约 `90.27%`。最终版本保持 canonical write
零 fan-out、访问时精确刷新、Bank Detail 行与 Cost 全局统计解耦、statistics fail-closed
和 Workbench active-generation 原子发布合同。

生产最终热访问中，Cost `scope=all/project_scope=all` 为 `714 ms`，
`scope=all/project_scope=active` 为 `447 ms`；两者均返回 `fresh` 和 fixture 精确数据。
最近 15 分钟 22 个 Cost worker 样本为 p50 `327 ms`、p95 `1537 ms`、p99 `3697 ms`。
跨月 active Cost child 的最慢 exact recovery 样本为 `4397 ms`，最终仍为 `fresh`。
本阶段不把已明确延期的硬 3 秒 SLO 当成正确性门禁。

## 实现

1. `PostgresReadModelRepository` 在 durable Workbench/Cost recovery 已
   pending/processing 时使用一次轻量 active-state 查询，直接返回精确
   `statistics=refreshing`；只有没有已知 recovery 时才执行完整 mismatch proof。
2. `CostStatisticsQueryService` 识别已有 recovery，不在每次页面轮询时重复执行
   Workbench/Cost enqueue 与全量证明。
3. Cost worker 等待 Workbench 的最小 defer 调整为 1 秒，减少依赖尚未完成时的
   0.25 秒热循环；其它 event/dependency 配置不变。
4. 全链路验证发现 completed `force_refresh=true` event 会永久覆盖后续新 freshness
   target。`RuntimeQueueRepository` 的 latest-done coalesce 现在排除该 completed force
   metadata；active force event 语义不变。修复位于共享原子队列边界，没有页面 fallback。

没有新增 cache、表、索引、migration、依赖、队列、worker、协调器、SSE、前端轮询或
写后 refresh producer。没有保留旧并行路径。

## 本地验证

- queue/gateway/worker/Cost/API/write 定向门禁：269 passed。
- Workbench/read-model/boundary 回归：402 passed。
- scope/bank boundary 回归：25 passed。
- 合计：696 passed。
- `ruff`/lint、docs gate、runtime boundary/diff gate：passed。
- 真实 PostgreSQL infrastructure slice：22 skipped；本机没有正式 PostgreSQL
  infrastructure，未用放宽断言隐藏。生产 test-owned fixture 补足真实 durable queue、
  worker、read model 和 API 证明。
- 未运行无关的 183 个浏览器测试或全量 CI。

## 生产验证

- 最终 active release：`main-b6e814b0-20260725192427`。
- test-owned fixture：`txn_imported_1278`（2026-02）与
  `txn_imported_1348`（2026-03），通过正式 confirm/withdraw API 执行并恢复 inactive。
- 最终 Workbench：
  - `2026-02`：`257 ms`、`fresh`、group 仅含 `txn_imported_1278`。
  - `2026-03`：`314 ms`、`fresh`、group 仅含 `txn_imported_1348`。
- 最终 Cost：
  - all：`714 ms`、`fresh`、精确包含 `txn_imported_1278`。
  - active：`447 ms`、`fresh`、精确包含 `txn_imported_1348`。
- 最后一次写链路产生的 Workbench 2026-02/2026-03 scope 均一次完成、无 retry，
  分别在 `2218 ms` 与 `2422 ms` 达到 fresh。
- Turnover 2026-02/2026-03 分别在 `244 ms` 与 `371 ms` 达到 fresh。
- System Audit：17 个页面已登记，16/16 业务页面通过；integrity `pass`、
  freshness `fresh`、queue `drained`、blocking issue 0。
- Durable outbox：pending/publishing/failed/publish_failed 全部 0。
- 15 个 read model：stale 0、unavailable 0。
- 24 个 required worker：全部 current/effective、available、idle。

RabbitMQ management metrics 当前仍为 `rabbitmq_metrics_unavailable`，但 RabbitMQ 不是
read model 状态事实源；PostgreSQL durable outbox/dirty scopes、System Audit 和所有 consumer
payload 已完成 authoritative 收敛。外部银行/OA/发票/ETC 来源完整性仍按既有合同为
`external=unknown`，不冒充 App 内部无法证明的外部事实。

## 七类测试责任

1. 业务核心单元：不适用；未修改金额、配对、标签或状态转换业务规则。
2. Service layer：已覆盖 Cost query、repository、queue 和 worker orchestration。
3. API contract：未改 response shape；现有 Cost/API 和写操作 contract 回归已通过。
4. Read model/cache/background job：已覆盖 active recovery、fail-closed、原子去重、
   completed force event、dependency defer、fresh/drained。
5. Frontend interaction：不适用；无前端代码或交互变化。
6. E2E business flow：生产 test-owned confirm -> access-time rebuild -> withdraw ->
   fresh recovery 已覆盖。
7. Existing regression：Workbench、Bank Detail、Turnover、Cost、scope policy、
   zero-fan-out 和 runtime boundary 已覆盖。

## 遗留风险

没有本阶段阻断项。硬 3 秒 SLO 仍是单独性能任务；跨月最慢 Cost recovery 样本为
`4397 ms`。RabbitMQ management metrics 和外部系统控制证据仍不可用/unknown，但不影响
PostgreSQL durable freshness 事实源与本次 App 内部正确性结论。
