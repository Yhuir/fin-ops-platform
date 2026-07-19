# 第 3 项：流水规则批量处理链路全量分析

## 范围

本项只处理 `/bank-flow-rule-batches` 页面中的批次操作子链路：

- 批次列表、筛选、分页与摘要；
- 批次详情；
- 选中流水提交；
- 单个内部往来批次提交；
- 单批撤回；
- “重置全部已提交”；
- 写后本页面重新显示新数据的收敛过程。

标签规则抽屉 `GET/PUT /api/bank-flow-rule-batches/tag-rules` 已在第 2 项闭环，本项禁止重新设计其业务行为。No-OA 批次、关联台、银行明细、批量账务及其他页面不是本项实现范围；共享 canonical relation 事实变化可以由既有 fan-out 影响它们的数据，但本页面不得写入它们的私有 read model 或调用它们的页面 service。

## 生产基线

20 次认证只读探测（另含 warmup）表明：

| 链路 | p50 | p95 | 结论 |
| --- | ---: | ---: | --- |
| 页面壳 | 112.421ms | 147.781ms | 快 |
| all 列表，page size 20 | 841.268ms | 965.789ms | 仅勉强低于旧 1s 门槛，不符合“非常高性能” |
| 详情（抽样批次） | 198.687ms | 254.178ms | 当前样本快，但存在随成员数增长的 N+1 风险 |
| Page Audit | 286.097ms | 367.993ms | `pass / fresh / drained` |

App Health 将列表 p95 分解为服务端 785.842ms、数据库 264.128ms、7 个查询；约 522ms 是数据库之外的 Python JSON 解析、重复遍历、摘要与标签解析开销。生产当前有 189 个可见批次，前端每页请求 200 条，因此用户真实页面会把全部批次载入、映射并渲染。

历史 worker 指标显示：month/incremental refresh p95 3317.018ms；`all` full refresh p95 28027.705ms。最近 15 分钟和 1 小时没有事件样本，因此不能把历史数据冒充当前写后实测，但它足以证明“等待所有 read model fresh 后再结束前端操作”会把后台延迟直接暴露给用户。

## 当前边界与 I/O

### 读路径

`BankFlowRuleBatchApiRoutes` → `BankFlowRuleBatchApplicationService` → `BankFlowRuleBatchReadModelRepositoryPort` → `read_model.bank_flow_rule_batch_rows`。

权威事实仍是 PostgreSQL 的银行流水、有效标签、正式关系和批次状态；列表只能读取本模块的 read model，不能在请求内重建 canonical facts。

### 写路径

Route 做权限和 HTTP 映射；application service 编排领域批次与 relation command；`WorkbenchRelationCommandRepositoryAdapter(save_repository=False)` 只把关系变更应用到内存快照；`PostgresStateStore.save_bank_flow_rule_batch_mutation(...)` 随后在一个数据库事务里持久化 changed relations 与 changed batches。

因此写路径已经具有一个正确的原子提交边界，不存在“双重数据库提交”。本项必须保留该边界，不新增第二套 UoW。

### 刷新路径

关系写入通过既有 durable outbox/dirty scopes 驱动 bank-flow、Workbench 与 relation read model。Bank-flow worker 按 month 或 all 读取 canonical bank rows、有效标签和正式关系，生成并发布 `read_model.bank_flow_rule_batch_rows`。PostgreSQL durable queue 是 freshness 事实源，Redis/RabbitMQ 不得替代它。

## 真实根因

### 1. 列表分页发生在 Python，而不是 SQL

`list_batches_payload(...)` 当前：

1. 使用 summary filters 读取一次全部匹配批次；
2. 使用页面 filters 再读取一次全部匹配批次；
3. `_list_bank_batch_rows(...)` 没有 `LIMIT/OFFSET`，并解析每行完整 JSON payload；
4. 两组结果拼接后逐批次检查 source versions；
5. Python 再全量计算摘要、反复解析标签与 Decimal；
6. 最后才切片分页。

在无额外筛选时，两次查询返回相同的 189 行，服务对 378 个 payload 做 stale 检查，再对 189 行做摘要和标签解析，即使 API 请求只需要 20 行。前端固定 page size 200，又让真实页面丧失分页带来的网络与渲染收益。这是列表近 1 秒的主因。

仓库已经存在 `bank_flow_rule_batch_source_versions_summary(...)`，但当前列表没有利用它，说明不需要新增缓存或表；只需把现有 SQL read model 的分页、count/aggregate 与 source-version proof 暴露为窄 read port。

### 2. 详情按成员逐条读取银行流水

`detail_payload(...)` 通过 `no_oa_bank_transaction_rows_by_ids(...)` 循环调用 `ImportNormalizationService.get_transaction(...)`。一个 N 行批次最多触发 N 次银行流水读取；抽样批次较小，所以当前 p95 尚快，但大批次会线性劣化。

现有 `PostgresCoreRepository.list_bank_transactions_by_ids(...)` 已提供一次 `ANY(text[])` 的批量读取，只是没有经 `PostgresStateStore` 与 import service 暴露。正确修复是复用该能力并保序，不创建新的事实表或通用查询框架。

### 3. “重置全部已提交”包含同步全量重建与逐 relation I/O

当前 reset 对每个 submitted batch 顺序执行 withdraw 和单 relation cancel；生产当前有 54 个 submitted batch。之后又按每个 affected month 同步调用 `refresh_batches(...)`，把 canonical rows、标签和 relations 重新载入并构建；最后才执行统一持久化。

这使 HTTP 延迟同时受批次数、月份数和每月流水量影响。现有 `WorkbenchRelationCommandService.cancel_relations_for_row_ids(...)` 已支持一次装载、一次取消多组 active relations、一次返回 changed case IDs；reset 应复用它。批次撤回的 durable commit 完成后，重新生成 draft 是 worker 的职责，不应在 HTTP 请求内同步重建。

### 4. 前端把其它页面的 freshness 当成本页面操作完成条件

提交路径已经在 command 成功后立即更新本地页面，并后台 reconcile；撤回和 reset 却同步等待 response 中所有 targets，包括 `workbench_relation` 与 `workbench` 的 `all + month` scopes，然后才刷新页面并解除全局操作遮罩。

共享 relation 事实确实应该 fan-out 到下游，但其它页面何时 fresh 不是本页面可操作性的 I/O。当前等待把历史 3–28 秒 worker 尾延迟直接转化为用户阻塞时间。正确边界是：

- foreground 只等待事务提交成功；
- 本页面立即显示已提交/已撤回的 committed state，或在 reset 后显示轻量 `同步中` 并禁止冲突操作；
- 只以 `bank_flow_rule_batch/<affected month>` 作为本页面后台 reconcile 条件；
- 完整 targets 仍广播给下游页面，但不阻塞本页面。

### 5. Bank-flow 运行链仍泄漏 no-OA 旧合同

全仓入口、route、service、worker、repository、前端、测试和文档扫描确认，bank-flow 可达链路仍包含：

- `no_oa_bank_transaction_rows_by_ids`、`no_oa_bank_batch_source_versions` 等旧命名调用；
- `NO_OA_BANK_BATCH_SCHEMA_VERSION` 被写入 `bank_flow_rule_batch_schema_version`；
- 新建 bank-flow batch 仍生成 `no_oa_batch_<hash>`；
- base `resolve_labels(...)` 给 bank-flow 列表写入 `免OA` display tag；
- relation idempotency key 使用 `no_oa_bank_batch` 前缀；
- route 依靠 `BANK_FLOW_RULE_BATCH_LEGACY_ERROR_CODES` 把内部 no-OA 错误翻译为 bank-flow 错误；
- bank-flow worker 实际构造 shared base application service，仍使用 no-OA 方法名和 reason。

这不是简单的命名美观问题：schema/source-version、ID namespace、错误合同和 UI tags 都属于可观察 I/O，旧逻辑已污染新链路。

## 生产级最简设计

### A. 专属分页 read port

在现有 `BankFlowRuleBatchReadModelRepositoryPort` 增加一个 bank-flow 专属 `read_page` I/O，返回：

- 当前页完整 batch payload；
- total；
- 按 batch type/status 聚合的 count 与 amount；
- source-version summary 和 readiness status。

PostgreSQL 使用现有表和索引完成 `LIMIT/OFFSET`、聚合与 source-version proof。Application service只对当前页补标签，并把聚合事实映射为既有 response summary。无新缓存、无新 read model、无 response shape 变化。

前端 page size 从 200 收敛为 50；仍用现有分页 UI。50 是页面可用性与渲染成本的生产折中，不引入虚拟列表。

### B. 详情复用 bulk transaction read

把既有 `list_bank_transactions_by_ids(...)` 逐层暴露为窄 port，application 一次取回并按请求 IDs 恢复顺序。空 IDs、未知 IDs、重复 IDs 继续使用现有合同；详情的标签和关系读取仍是批量 I/O。

### C. Reset 复用 bulk cancel，删除同步 rebuild

Reset 只执行：

1. 在内存领域服务中把目标 submitted batches 改为 withdrawn；
2. 收集目标 row IDs，调用一次既有 bulk cancel；
3. 通过现有 `save_bank_flow_rule_batch_mutation(...)` 一次原子保存关系与批次；
4. 返回 affected months/targets；
5. 由既有 durable worker 生成新的 unsubmitted drafts。

不新增 bulk endpoint、queue type、后台任务或第二套 transaction owner。

### D. 统一前端写后收敛

submit、withdraw、reset 都以 command response 为 foreground 完成点。单批操作可根据 response `batch` 立即更新本地列表；reset 在切换 `unsubmitted` 后显示现有轻量 background refreshing 状态，并在本模块 month targets fresh 后 reload。期间只禁用本页冲突写按钮，不使用新的 solid modal。

### E. 清理可达旧链，保留历史身份兼容

- 为 bank-flow service 显式配置 `BANK_FLOW_RULE_BATCH_SCHEMA_VERSION`、`bank_flow_rule_batch_` 新 ID 前缀和 bank-flow error/idempotency namespace；
- bank-flow application/worker 只调用中性或 bank-flow 专属方法；
- `resolve_labels` 输出 `流水规则`，不再输出 `免OA`；
- 删除 route 的 legacy error translation map；bank-flow service直接产生正式错误码；
- worker 构造 bank-flow 专属 application boundary；
- 加 architecture guard，禁止 bank-flow route/application/worker/frontend出现 `no_oa`、`NO_OA`、`免OA`（明确的历史 ID 接受测试除外）。

已存在的生产 `no_oa_batch_*` batch/relation IDs 是持久化身份，不做重命名迁移；route、repository 和领域服务必须继续按原 ID读取/撤回。新的 draft 在下一次 scoped refresh 后使用 bank-flow 前缀，旧 draft 自然被投影替换；submitted/withdrawn 历史 ID 保持。No-OA 模块仍需要自己的旧代码与 ID，不属于可删除对象。

## 明确不采用

- 不新增 Redis 缓存、物化表、投影类型、消息总线或 worker。
- 不新增 UoW；保留现有单事务持久化 owner。
- 不让 API 在写请求里等待 Workbench 或其他页面 fresh。
- 不做生产历史 ID 批量迁移。
- 不把 worker 改成复杂的 row-level delta 引擎；先优化现有 month-scoped 查询与在线直写，真实 PostgreSQL若仍未达门槛，才在同一 worker 内优化现有 bulk SQL。
- 不修改第 2 项标签规则行为，不修改 No-OA 或其它页面 read model。

## 性能与正确性门槛

- 页面壳生产 p95 ≤ 500ms。
- all/month 列表 API（page size 50）生产 p95 ≤ 500ms，服务端 p95 ≤ 250ms；查询数有明确上限且不随可见批次数增长。
- 详情 50/200 rows 的真实 PostgreSQL查询数保持常数；生产抽样 p95 ≤ 500ms。
- 单批 submit/withdraw command生产 p95 ≤ 1000ms；command 返回后本页 committed state ≤ 1000ms 可见。
- reset 响应不再包含同步逐月 rebuild，真实 PostgreSQL耗时与月内总流水量解耦；生产安全样本或等价 staging/事务回滚样本 p95 ≤ 1500ms。
- bank-flow month read model 从 committed mutation 到 fresh：p95 ≤ 2000ms，硬上限 3000ms；若实测未达标，不发布“高性能完成”。
- Audit 始终 `pass`；刷新期间诚实显示 refreshing/stale，完成后 `fresh / drained`。
- No-OA、Workbench、银行明细、流水规则配置与其它页面的合同、Audit 和 read model 不回归。

## 分析结论

问题不是缺少缓存，而是已有 SQL read model 被全量读取两次、详情没有使用已有 bulk API、reset 在 HTTP 内做同步重建，以及前端跨越了本页面 freshness 边界。使用现有模块能力即可形成生产级闭环；无需扩展基础设施。
