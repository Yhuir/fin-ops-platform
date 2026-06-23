# Read Model 模块化重构前分析

**日期:** 2026-06-23
**GSD 阶段:** pre-implementation-analysis
**范围:** read model 查询、刷新、状态、事件、权限、测试合同和遗留链路隔离；本文件不启动代码重构。

## 结论

可以先做 read model 模块，而且建议把 read model shared foundation 提前到下一阶段。你现在遇到的“一个页面更新了，另一个页面没有同步更新”的问题，本质上不是文件拆分问题，而是 read model 的事实源、刷新边界、freshness proof、状态暴露和页面读取合同没有被统一治理。

不建议先一次性把所有页面的 read model 全部拆完。正确顺序是先建立统一 read model 边界和 manifest，再按 read model key / 页面小步迁移。这样每次迁移都有可验证的输入、输出、状态、事件、readiness、权限和测试合同，不会把全局重构做成不可验证的大改。

应该统一管理，但统一管理的是 contract / registry / gateway / status / queue / tests，不是把所有 read model 逻辑塞进一个新的大 service。每个 read model 仍然要有自己的 owner、repository port、projection builder、刷新 scope、readiness source 和回归测试。

## 当前事实

已存在的核心边界：

- `ReadModelQueryGateway`: 统一处理 read model 查询的 freshness/status/enqueue 语义。
- `ReadModelRefreshGateway`: 统一 normalize、validate、dedupe 后再进入 durable queue。
- `ReadModelScopePolicyRegistry`: 登记 read model scope policy。
- `APP_STATUS_READ_MODEL_REGISTRY`: 登记 app status/read model readiness 可见性。
- `runtime_worker_registry.py`: 登记 worker、readiness、dirty scope、SLO smoke 关系。
- `operation_freshness_barrier.py`: 写后读的 operation barrier runtime snapshot。
- `job.outbox_events`、`job.read_model_dirty_scopes`、`read_model.app_status_readiness`: read model refresh 的 durable truth。

主要结构风险：

- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py` 约 11329 行，是多 read model SQL 和 payload 装配的集中点；它已经是最大重构风险之一。
- gateway 和 registry 已经存在，但 per-read-model manifest、repository ownership、projection IO contract 还没有形成可自动审计的闭环。
- 不能让页面绕过 freshness/status/enqueue 边界直接读取旧 payload，也不能让页面把 stale/missing/schema mismatch 的空数据当成真实空列表。
- `workbench` 有 active generation 原子发布模型，不能机械套成普通 read model rebuild。

## 目标边界

每个 read model key 必须最终登记以下合同：

| 合同 | 要求 |
| --- | --- |
| 输入 | query params、filters、pagination、sort、scope keys、expected schema/source version、writer 产生的 dirty scope/event |
| 输出 | payload、`read_model_status`、`refresh_enqueued`、stale/missing/failed reason、source/schema version、affected scopes |
| 状态 | fresh、refreshing、stale、missing、failed、unavailable、schema mismatch、source mismatch |
| 事件 | outbox event、dirty scope、readiness publish、worker heartbeat、operation barrier target |
| read model | projection owner、repository port、builder/worker owner、refresh mode、partition key、scope key、full rebuild fallback |
| 权限 | API/page 继续拥有权限判断；read model 边界不得绕过 session/capability gating |
| 测试合同 | gateway、service、API、read model、worker、frontend stale/loading、跨页面回归、legacy contamination guard |
| 模块边界 | page/service 不直接 SQL 写 `job.outbox_events` 或 `job.read_model_dirty_scopes`；生产 SQL runtime 不 fallback 到旧 live scan |

## 统一管理的形状

建议新增或收敛成一个 read model manifest 层。manifest 不替代具体实现，只作为自动审计和迁移事实源。

每个条目至少包含：

- `read_model_key`
- owning module / page
- query gateway contract
- refresh gateway scope policy
- repository port / SQL owner
- projection builder / worker
- durable truth tables
- app status readiness mapping
- operation barrier target mapping
- partition key / scope key
- schema version / source version providers
- refresh mode: scoped incremental、partitioned scoped、active generation、full rebuild fallback
- permission owner
- tests owner
- legacy paths and deletion condition

## 页面和 read model 初始清单

本轮分析把以下 key 视为必须进入 manifest 的第一批对象：

| Read model key / family | 初始目标策略 | 说明 |
| --- | --- | --- |
| `workbench` | active generation + scoped publish | 保留原子发布，不机械改成普通 query gateway |
| `workbench_relation` | scoped incremental | 关系确认/撤销必须触发精确 affected scope |
| `bank_detail` | partitioned scoped + scoped incremental | 月份、账户、自动标签规则版本需要进入 source/freshness 合同 |
| `bank_account_balance` | partitioned scoped | 账户/月度余额聚合应与银行明细 dirty scope 对齐 |
| `pending_invoice` | scoped incremental | list/detail/drawer 不能绕过 freshness status |
| `oa_pending_payment` | scoped incremental | 与 OA relation / pending invoice 共享 affected scope |
| `invoice_lifecycle` | scoped incremental | 输入/输出票据状态变更必须发布可追踪 source version |
| `input_invoice_usage` | scoped incremental | 使用率、勾稽、匹配状态必须有旧链路隔离 |
| `output_invoice_collection` | scoped incremental | collection 状态和 ledger/summary 影响需要登记 |
| `cost_statistics` | partitioned scoped rollup | summary 查询和 rollup 刷新要拆出 repository port |
| `tax_offset` | partitioned scoped | 抵扣月份/税期是天然 partition key |
| `turnover_ledger` | partitioned scoped | 台账写入和银行标签变更需要明确刷新范围 |
| `no_oa_bank_batch` | scoped incremental | 批次识别/过滤不应 live scan 替代 read model 状态 |
| `search` | partitioned scoped index | search payload 必须带 freshness/status，不返回伪 fresh |

Import path、settings、app health 也会影响 read model，但不应直接作为第一批 read model key 处理：

- Import path 先登记 job-scoped source event 和 affected scopes，只有性能证据足够时才进入 Go processor admission。
- Settings 先登记 source version provider 和 targeted invalidation，不把 settings 页面改成 read model。
- App health/current-effective config 是 runtime projection，可参与 readiness/status，但不能替代业务 read model freshness proof。

## 推荐推进顺序

1. `read-models:manifest-and-boundary-inventory`
   - 只做 manifest / registry / owner / IO contract 盘点。
   - 不改变业务行为，不迁移 SQL，不引入 Go。
   - 产出每个 key 的输入、输出、状态、事件、权限、测试、legacy path 表。

2. `read-models:query-gateway-contract-and-status-parity`
   - 确认每个页面读取 read model 时都有统一 status/freshness/enqueue 语义。
   - 补 guard，禁止页面读旧 payload 却伪装 fresh。

3. `read-models:refresh-gateway-force-refresh-and-operation-barrier`
   - 把 force refresh、scope policy、operation barrier target 统一到同一边界。
   - 确认写后读必须有 affected scope 和 freshness proof。

4. `read-models:repository-port-and-sql-owner-split-plan`
   - 先从 `read_models.py` 建立 owner map 和 repository port。
   - 不做一次性大拆；按 key 小步拆分并保持 API shape。

5. Per-key 迁移
   - 先迁移最容易制造跨页面 stale bug 的 read model：`workbench_relation`、`pending_invoice`、`oa_pending_payment`、`bank_detail`。
   - 再迁移 summary/rollup：`cost_statistics`、`tax_offset`、`turnover_ledger`。
   - 最后处理 search/no-oa-batch 等广义读侧。

6. Legacy removal and contamination guards
   - 删除或隔离旧 live scan、旧 refresh helper、旧 direct SQL queue writes。
   - 所有保留 legacy 必须标记 `compat-only`、owner、调用者、删除条件和防污染测试。

7. Go/Fiber/Go Worker admission
   - 只有 read model contract 稳定后才进入 Go candidate。
   - 候选仍是 Workbench compute、read model builder、summary rollup、large import path、Go Worker + PostgreSQL dual queue。
   - Go 不是 read model 语义替代品；性能优化仍必须服从 manifest、freshness 和 durable queue 合同。

## 是否先把所有页面 read model 模块化

不应该一次性完成所有页面级迁移，但应该先完成所有页面/read model 的 manifest 盘点。区别如下：

| 做法 | 是否推荐 | 原因 |
| --- | --- | --- |
| 先写全量 manifest / IO contract / owner map | 推荐 | 低风险，能让后续每个模块自动推进时有边界和验收标准 |
| 先把所有页面 read model 代码一次性拆完 | 不推荐 | 回归面过大，容易把 freshness、权限、API shape、worker readiness 一起打坏 |
| 先做一个页面试点，不建统一边界 | 不推荐 | 会继续产生页面级补丁，无法解决跨页面不同步 |
| 先建统一边界，再按 key 小步迁移 | 推荐 | 能兼顾全局一致性和每次可验证 |

## 完成定义

Read model 模块化重构不能只按“文件拆完”算完成，必须满足以下条件：

- 每个 read model key 都有 manifest 条目和 owner。
- 每个 query path 都通过统一 freshness/status/enqueue 边界，或有明确等价合同。
- 每个 refresh path 都通过 `ReadModelRefreshGateway` / scope policy registry / durable queue，或在同一事务内承担等价 scope contract。
- 每个 write path 都能声明 affected scopes，并通过 operation barrier 或 readiness 状态证明后续页面可见性。
- 每个 read model 都有 repository port / projection builder / worker owner。
- `read_models.py` 的 SQL owner 被拆分或至少被 manifest 强绑定，不能继续作为不可审计的共享大仓库。
- 旧 live scan、旧 direct queue write、旧 refresh helper 被删除或隔离，且有 guard 防止回流。
- 测试覆盖七类测试中适用项，尤其是 read model/cache/background job、API contract、跨页面回归和 legacy contamination guard。
- 无本地 `PGSQL_URL` 和 staging DB 时，生产证据只能标记为 deferred；不能把未验证的生产 DB/worker 闭环标为完成。

## 风险与约束

- 不要把统一管理误解成单一 read model god service。
- 不要用“刷新全部”掩盖 scope 设计错误；`all` 可以是 fan-out command，但 queryable `all` 必须有 freshness proof 或 aggregate proof。
- Redis 只能缓存 fresh gate 之后的 payload；RabbitMQ 只能是 transport/wakeup，不能作为 read model 状态事实源。
- 生产 root SSH 可用于只读验证，但自动流程不能读取 secret、不能生产写入、不能执行 worker 重放。
- 没有本地 `PGSQL_URL` 和 staging DB 仍然可以推进代码和本地 contract/test；真实生产闭环证据必须独立记录为 deferred 或在审批后执行只读验证。

## 对当前自动队列的建议

把下一阶段从 `reconciliation-workbench:amount-check-query-contract` 调整为 `read-models:manifest-and-boundary-inventory` 是合理的。Workbench amount check 仍然重要，但应该在 read model foundation 之后推进，否则会继续以单页面方式局部修补。

新的 read model 主线应先产出全量 manifest，再进入逐 key 迁移。这样后续无人值守流程才能按状态机自动推进：分析 -> 实现 -> 审阅 -> 更新状态 -> 生成下一 prompt，而不是靠临时判断选择下一个页面。
