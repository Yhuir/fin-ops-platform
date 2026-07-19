# 批量账务性能全量分析

日期：2026-07-20

## 结论

批量账务当前没有前端重复加载，也没有 worker 堵塞。生产 `GET /api/batch-accounting` 的主要慢点是 `workbench_relation` 查询端按 scope 逐个证明 freshness：一次请求产生约 52–66 次数据库查询。其次，未提交列表会读取所有 OA 附件发票，再在 Python 中关联到当前 OA 候选；这会随历史数据增长而放大。

首次发布后 query count 已降到 p95 `10`，但 40 样本 unsubmitted HTTP p95 仍为 `612.217ms`；dashboard 显示 API 内部 p95 `400.374ms`、DB p95 `256.256ms`，压缩响应仅 `3629 bytes`。剩余根因是银行候选 SQL 对结构化 `counterparty_name` 与两个历史 payload 字段做 `OR`，使既有 `workbench_rows_bank_counterparty_scope_idx` 无法稳定命中。当前 projection/Audit 已保证结构化列，因此 payload fallback 是可删除旧链，不需要新索引或缓存。

本轮应保留现有 Workbench + workbench_relation 事实源，不新增独立 read model、缓存、表、索引、队列或 worker。最小而完整的生产方案是：

1. 新增批量账务专用的 relation 批量读取 I/O，一条 SQL 同时证明 12 个或候选涉及的全部 scope。
2. 未提交候选只读取当前 OA IDs 对应的附件发票。
3. 银行候选只读取 Workbench projection 的结构化 `counterparty_name`，删除两个 JSON fallback，让既有复合索引生效。
4. 批量账务不再调用通用的逐 scope relation 读取入口；通用入口继续服务其他页面，行为不变。

## 生产基线

- 页面 shell：p95 `104.966ms`，通过 `500ms` 门槛。
- 未提交 2026：p95 `638.061ms`，20/20 fresh、0 enqueue，未通过 `500ms` 门槛。
- 已提交 2026：p95 `390.986ms`，通过 `500ms` 门槛。
- Page Audit：p95 `375.765ms`，通过 `1000ms` 门槛。
- `/api/batch-accounting` 52 个生产样本：DB query count p50 `52`、p95 `66`、p99 `71`；SQL execute/fetch p95 `349.462ms`，connection acquire p95 `0.905ms`。
- `workbench_relation` worker：近 15 分钟/1 小时 refresh p95 `20.391ms`、stale `0`、unavailable `0`，不是当前瓶颈。

## 当前链路与边界

输入 I/O：

- `GET /api/batch-accounting?bank_year=YYYY&bucket=unsubmitted|submitted`
- Workbench active generation：批量账务银行候选、日常报销 OA、OA 附件发票。
- workbench_relation：候选是否已关联、年度已提交 relation、freshness/source_versions。

输出 I/O：

- 既有 API response shape、分页、`read_model_status`、`read_model_scope_keys`、`stale_reasons`、`refresh_enqueued`。
- 既有前端 loading/empty/error/refreshing 行为。

事实源：

- 业务 relation 事实：`app.workbench_pair_relations`。
- 关系读模型：`read_model.workbench_relation_*`。
- freshness/refresh 事实：PostgreSQL durable queue `job.read_model_dirty_scopes` / `job.outbox_events`。
- 候选行：Workbench active generation。

明确不改变：

- submit/withdraw command service、canonical relation 写入、affected scopes、derived lifecycle。
- 其他页面的 WorkbenchRelationReadFacade 通用 `get_by_row_ids`、`list_by_month` 和 worker/read model 合同。
- API DTO、权限、页面状态机和业务筛选规则。

## 根因证据

### 1. relation freshness N+1

`_workbench_relation_payload_from_rows(...)` 对每个 scope 分别执行：

1. 查询 `read_model.workbench_relation_scopes`。
2. 查询 `job.read_model_dirty_scopes` 的当前状态。

年度 count 为 12 个 scope 的 24 次证明 + 1 次 count。年度 list 先证明 24 次，读 groups 后又证明 24 次。候选 row lookup 还会再次按实际/hint scope 逐个证明，因此生产观测到 p95 66 次查询。

### 2. OA 附件查询未按候选收窄

未提交 loader 已经先得到 OA 候选，但附件 SQL 仍读取所有非 `all` scope 的 `oa_attachment_invoice`，最后才在 service 中构建 OA→invoice 关系。当前生产数据量尚小，但这是确定性的扩张风险，也违反“页面读取应由当前输入界定”的 I/O 约束。

### 3. 前端、连接与 worker 不是根因

- 前端一次依赖变化只发一次 list 请求，没有重复 fetch。
- connection acquire p95 小于 1ms。
- worker refresh p95 约 20ms 且无 stale/unavailable。

因此不应增加前端轮询、缓存、worker 并发、数据库连接池或新 read model。

## 旧代码识别与移除范围

本轮要从批量账务链路移除：

- BatchAccountingService 对通用 `get_by_row_ids` 的依赖。
- 年度 count/list 内逐月 `_workbench_relation_payload_from_rows` 证明以及 list 的第二次重复证明。
- 未提交 loader 中无 OA ID 约束的全量附件 SQL。
- 银行候选 SQL 中绕过结构化投影列的 `payload.counterparty_name` / `payload.counterparty_name_raw` fallback。

不会删除：

- 通用 `get_by_row_ids` 和逐 scope payload 逻辑，因为仍有其他合法调用方；只禁止批量账务继续进入该旧路径。
- submit/withdraw 已有窄读取和 canonical command 路径。

静态 guard 必须证明批量账务 service 使用专用 relation I/O，loader 不再包含无 OA ID 条件的附件读取，并且银行候选只读取结构化 `counterparty_name`。

## Grill-me 三轮审阅

### 第一次：正确性与一致性

- 批量 proof 必须保持原顺序、状态优先/覆盖行为、`missing_scope:*` 和 `refreshing|stale:*` reason 格式。
- source_versions 仍取第一个存在且非空的 scope metadata；没有时才使用 rows/groups fallback。
- 非 fresh 仍由既有 facade 统一 enqueue；不得伪装 fresh。
- 年度 12 scope 合同和空 scope 行为不变。
- 结论：可实施，但必须以“输出等价”和 fresh/missing/refreshing/stale 测试作为门禁。

### 第二次：模块隔离与旧链删除

- 若直接优化通用 helper，会扩大对其他页面的运行时影响面，不符合本轮隔离目标。
- 因此增加 Batch Accounting 专用 repository/port/facade 方法；其他页面的通用方法不改调用关系。
- 可以复用一个纯内部 payload 组装 helper，但批量方法必须显式拥有自己的批量 scope proof I/O。
- 旧无界附件 SQL直接替换，不保留 fallback。
- 结论：边界清晰，只有 Workbench/read-model 作为显式共享事实，不会改变其他页面的功能输出。

### 第三次：性能、复杂度与运维

- 未提交目标固定约 8 次查询：3 个候选读取 + 3 个专用 relation lookup + 2 个年度 count。
- 已提交目标固定约 6 次查询：1 个银行读取 + 2 个年度 relation list + 3 个 relation detail lookup。
- 不新增基础设施、schema 或 migration，回滚为代码版本回滚。
- 只有部署后 p95 仍大于 `500ms` 且 EXPLAIN/数据库证据明确指向候选 SQL 时，才进入后续 server-side candidate paging/index 优化；本轮不提前实现。
- 结论：方案不是过度设计；它直接删除已量化的 N+1 和无界读取，并保留完整 freshness、审计、回滚和隔离闭环。

## 验收门槛

- 页面 shell p95 `<=500ms`。
- unsubmitted/submitted GET p95 `<=500ms`，目标 `<=300ms`；20 次全部 2xx。
- fresh 样本 `refresh_enqueued=false`，状态与 scope 合同保持一致。
- Page Audit p95 `<=1000ms`，结果 pass/fresh/drained/ready/0 issue。
- DB query count 不随 scope/candidate 月份数线性增长；单请求目标 `<=10`。
- command API p95 `<=1000ms`，committed-to-fresh p95 `<=2000ms`、hard max `3000ms`；生产写验证受全局 App Health preflight 门禁约束，门禁未通过时必须延后到最终系统门，不得绕过。
- 直接模块及关联台、银行明细、流水统计/成本统计 Page Audit 无回归。
