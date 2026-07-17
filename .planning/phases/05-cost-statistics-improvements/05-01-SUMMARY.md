---
phase: 05-cost-statistics-improvements
plan: 01
status: complete
completed_at: 2026-07-16
next_state: IMPLEMENTING
requirements:
  - COST-PERF-01
  - COST-FRESH-01
  - COST-AUDIT-01
  - COST-LEGACY-01
---

# 05-01 执行摘要：成本统计全链路事实预检

## 结果

第一轮 bounded discovery 已完成。现有生产级设计与真实代码总体一致，没有发现需要增加平台级组件的理由；真正需要的复杂度只有成本自有结构化查询边界、durable source-version CAS、view-specific API、成本页局部锁定遮罩和成本自有 Audit SQL。设计不是为了“完整”而堆层，而是分别对应已量测的全量 payload 热点、已经出现的版本 mismatch、页面旧数据误用风险和 12–35 秒 Audit。

本轮没有修改业务代码、schema、测试或生产数据，没有部署、暂存、提交、建分支或 push。唯一下一状态是 `IMPLEMENTING`；后续 execution prompt 尚未生成。

## Grill-me 决策

| 问题 | 证据结论 |
| --- | --- |
| 目标 | 用户已确认 SLO；设计文档给出 cold/warm/data-ready、`active:all`、Audit 和 write-to-fresh 门槛。 |
| 直接模块 | `cost-statistics` 页面、API/query、cost projection/repository、cost worker、cost Audit。 |
| 直接上游 | Workbench active generation、Bank Detail fresh scope、成本 Settings versions；它们只在 owner 成功发布后 fan-out。 |
| 输出 I/O | fresh 时返回成本自有 view/page/detail/export；non-fresh 时返回状态并 enqueue，前端锁定成本内容区。 |
| 事实源 | canonical PostgreSQL facts；PostgreSQL dirty scope/outbox 是刷新状态事实源；Redis 不是 freshness 权威。 |
| 隔离 | 不改其他页面 read model、全局 App Shell、全局 overlay、共享 pool 或其他页面 API。 |
| 旧链路 | live/local service、warmup、full payload、无版本缓存、旧 client/route、混合 Audit 和对应 tests/docs/deploy 均已定位。 |
| 回滚 | additive schema、同 release 切换、旧 schema fail-closed、回滚 artifact 重建；代码中不保留双读 fallback。 |

## 当前真实链路

```text
CostStatisticsPage
  -> frontend api.ts /api/cost-statistics/explorer
  -> routes_cost_statistics.py
  -> CostStatisticsQueryService
  -> ReadModelQueryGateway
       -> request-time expected source versions
       -> Redis versioned payload
       -> PostgresSummaryReadModelRepository.get_cost_statistics_view
            -> parent JSON
            -> cost_statistics_rows 全 scope 查询
            -> dirty scope 查询

Upstream owner publish/settings write
  -> ReadModelRefreshGateway / transactional queue writer
  -> job.outbox_events + job.read_model_dirty_scopes(source_version)
  -> CostStatisticsReadModelRefreshService
  -> CostStatisticsSqlProjectionBuilder
  -> save parent + rows + Redis
  -> complete dirty scope
```

边界方向是正确的：页面不直接读 canonical facts，refresh 通过 durable queue。然而读路径和发布版本语义仍有明确缺口。

## 已证明的性能根因

1. `PostgresSummaryReadModelRepository.get_cost_statistics_view(...)` 读取 parent 后，会按 scope 无分页取出全部 `cost_statistics_rows`，再在 Python 重组完整 explorer。
2. `bank_flow_time_rows` 仍嵌在 parent JSON；无法使用结构化索引进行分页、点查或 streaming export。
3. `CostStatisticsQueryService` 在请求时重新读取 Settings、Workbench 和 Bank Detail source versions，再执行 gate；这不是短单查询热路径。
4. `get_transaction_detail(...)` 读取 `all` explorer 后分别扫描 cost rows 和 bank-flow rows。
5. 前端 `api.ts` 维护 5 分钟 `Map` cache；页面初始化和 scope effect 都先消费该缓存，它不能证明跨用户/跨设备 freshness。
6. `CostStatisticsPage` 首屏除当前月份 explorer 外，还无条件预取 `active:all` 作为 export reference；现有量测中该 payload 约 765KB decoded。
7. 前端拿到完整 arrays 后继续 map、filter、group；server serialization、网络传输、JS mapping 和 React commit 同时随全期间数据增长。

因此目标路径必须是“单次短 gate + view-specific indexed query + bounded page”，而不是增加缓存层或扩大数据库连接池。

## 已证明的 freshness / Audit 根因

现有 `ReadModelQueryGateway` 能在 schema/source/dirty 不匹配时返回 non-fresh，并且只把 fresh payload 放入 versioned Redis；这部分应复用。

真正缺口在成本 worker：

- `CostStatisticsReadModelRefreshService.handle_runtime_event(...)` 没有在重建前校验 event `source_version`。
- 重建后、发布前后都没有再次确认该 event 仍是当前版本。
- `complete_read_model_refresh(...)` 调用未传 `source_version`；相比已经正确传版本的 Bank Detail worker，成本 worker可能错误完成更高版本 dirty scope。
- `_publish_cost_statistics_scope(...)` 直接保存 rows/parent 和 Redis，没有在同一 repository transaction 中比较 stored queue version 与 event version。
- `RuntimeQueueRepository.complete_read_model_refresh(...)` 和 `read_model_refresh_is_current(...)` 已提供可复用版本能力，但 `read_model_refresh_is_current` 当前读取任意单 row 且无显式最高版本排序，只适合作为 precheck；正确性必须由发布 CAS、版本条件完成和 read gate 共同承担。

Audit 当前在通用 `page_business_audit.py` 内依次运行 13 类检查，成本分支还递归执行完整 Workbench integrity 和 Bank Detail 的 8 类检查。大量 cost SQL继续解析 parent JSON 中的 `bank_flow_time_rows`。这解释了 Audit 在队列 drained 后仍需 12 秒以上；而 `cost_statistics_upstream_source_versions_mismatch` 是真实发布收敛问题，不能通过隐藏或放宽 Audit 修复。

## 旧模块和删除责任

| 类别 | 当前 live 证据 | 完成条件 |
| --- | --- | --- |
| 本地 read model | `cost_statistics_read_model_service.py`，projection 临时实例化，server/tests 引用 | projection 直接写 cost repository；迁移有效规则后删 module/import/server field/tests。 |
| 旧 live service | `cost_statistics_service.py` 仍被 server 初始化，route/query tests 仍引用 | 规则进入 projection/repository contract 后删除，不保留 fallback。 |
| runtime warmup bridge | `cost_statistics_runtime_service.py`、server delegate、App Health/job registries、background job UI/tests/docs | durable cost refresh 完全接管后删除 warmup job、labels、recovery/delegate 和 fixtures。 |
| 无版本 cache key | projection/runtime 删除或写 `cost_statistics:explorer:{scope}`、`cost_statistics:month:{scope}` | 只允许 gate 后的版本化 view cache；静态 guard 阻止回归。 |
| 混合 owner | `cost_tax_sql_projection.py` 同时拥有 cost 与 tax builder | 拆回 cost owner；Tax Offset 行为和测试不变后删除混合文件。 |
| 全量 payload | parent JSON、query/rebuilder/Audit/tests/docs 使用 `bank_flow_time_rows` | 一张 cost bank-flow rows 表接管；parent 只留 metadata/summary。 |
| 前端旧 cache/prefetch | `costExplorerCache`、`getCached...`、页面 `active:all` effect | 删除 JS TTL cache 和全期间首屏预取；保留 HTTP revalidation。 |
| 详情全量 scan | query `get_transaction_detail` 读取 `all` 并两次线性扫描 | repository canonical identity 点查替代。 |
| 旧 API/client | `/api/cost-statistics`、`/projects/{name}`、`fetchCostStatisticsMonth`、`fetchProjectCostStatistics` | 部署前核对真实 access log/owners；无调用后删除 route/client/DTO/tests。 |
| 通用 Audit 大分支 | `page_business_audit.py` 的 cost contract、SQL 分支和 dependency recursion | cost-owned repository 以最多四组集合 SQL接管；统一 envelope 保留。 |
| 当前文档/部署登记 | cost-tax compatibility、warmup、旧 response shape 分散在 docs/deploy/tests | 随代码迁移同步；历史归档保留但不得描述为 current fallback。 |

税金抵扣仍依赖混合 projection 文件中的 tax builder 和 cost-tax 兼容登记，因此删除必须是“先迁出 tax owner，再删混合 owner”，不能机械删文件。

## 反过度设计结论

保留的五项复杂度都有当前证据：

1. 一张 `cost_statistics_bank_flow_rows` 表：解决 JSON 内银行流水无法索引分页的问题。
2. queue source-version CAS：解决已出现的 upstream version mismatch 和旧 event 竞态。
3. view-specific cursor API：解决 `active:all` 全量传输和前端重复聚合。
4. cost-owned Audit repository：解决通用 13 类检查叠加跨域检查的 12–35 秒耗时。
5. cost-local lightweight lock overlay：在 non-fresh 时阻止用户误用旧数据，不影响其他页面。

不新增 cost-specific SSE、WebSocket、Kafka、前端事件总线、通用 overlay 框架、OLAP、多张预聚合表、year scope、分布式锁、虚拟列表依赖、`/v2` 并行 API、全局 pool 改造或定时全量重建。已打开页面复用现有 App Health SSE 和 5 秒 fallback poll。

结论：设计简洁但不是简陋；没有发现需要删去上述五项中的任何一项，也没有证据支持增加第六项平台能力。`performance-freshness-lock-overlay-design.md` 无需因本轮代码核对而改写。

## 未决生产证据

以下事项必须保留到统一部署窗口，当前不能伪造闭环：

- 旧 summary/project endpoint 覆盖至少一个正常业务周期的生产 access log，或所有 owner 显式确认无外部消费者。
- 生产 active/historical `cost_statistics_cache_warmup` job 清点。
- legacy unversioned Redis key 命中/残留清点。
- schema migration、read model rebuild、queue drain 和 rollback rehearsal。
- 生产 SLO、Audit 连续通过、跨用户 freshness 和其他页面无回退验证。

这些不是当前实施阻塞项，但都是进入 `DEPLOYMENT_HOLD` 后解除部署门禁的必要条件。

## 七类测试责任

本轮只做文档化 discovery，没有运行时行为变化，因此没有新增实现测试；七类实现测试在后续均适用：

| 类别 | 后续责任 |
| --- | --- |
| 1. 业务核心单测 | project/expense/tag/direction、scope/source version、empty/duplicate/boundary。 |
| 2. Service 层 | repository page/detail/export、fan-out、CAS、Audit、partial failure。 |
| 3. API contract | fresh 200、refreshing 202、cursor/filter、权限、ETag/304、export errors。 |
| 4. Read model/cache/worker | 旧 event、rebuild 中再次写、parent shards、Redis gate、条件完成。 |
| 5. Frontend interaction | initial/refreshing/stale/error/fresh/empty、inert/focus/portal/reduced motion、last-response-wins。 |
| 6. E2E | owner write -> durable queue -> cost lock -> fresh -> 新值 -> Audit pass。 |
| 7. Regression | Workbench、Bank Detail、Tax Offset、App Status、权限、导出和其他 read models 不回退。 |

## 共享工作树保护

开始时存在以下其他 thread 文件，均未修改：

- `docs/modules/oa-pending-payments/README.md`
- `.planning/phases/04-reconciliation-workbench-improvements/04-PLAN.md`
- `docs/modules/oa-pending-payments/performance-integrity-design.md`

执行期间其他 thread 又新增了以下文件，本轮同样未读取或修改：

- `.planning/phases/04-reconciliation-workbench-improvements/04-GOAL-PROMPT.md`
- `.planning/phases/08-oa-pending-payments-improvements/08-PERFORMANCE-INTEGRITY-GOAL-PROMPT.md`

成本设计文档在开始时已经是未跟踪文件，本轮只读复审，未改写。

## 验证

- CodeGraph：index healthy，目标文件无 pending sync。
- whole-repo scan：覆盖 backend、web、tests、docs、deploy、scripts。
- `git status --short`：用于确认共享 dirty baseline 和本轮新增文件。
- `git diff --check`：作为本计划最终机械检查。
- 未运行 lint/backend/frontend tests：本轮无运行时代码变化；这些验证从第一个实现切片开始成为硬门禁。

## 唯一下一状态

`IMPLEMENTING`

理由：设计已被真实代码证据支持，边界、I/O、旧链路、测试责任和回滚均已明确；剩余事项是本地实现与验证，不需要继续开放式 discovery。按照主控约束，本摘要不生成后续 execution prompt，也不提前承诺实施顺序之外的具体改动。
