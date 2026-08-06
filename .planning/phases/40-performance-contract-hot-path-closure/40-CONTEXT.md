# Phase 40: 性能合同与核心热路径闭环 - Context

**Gathered:** 2026-08-01
**Status:** Ready for additional planning
**Source:** User-approved full-codebase performance audit

<domain>
## Phase Boundary

在不新增 Worker、页面 Read Model、Redis 缓存、Search projection 或通用查询框架的前提下，补齐目标规模/并发/浏览器性能证据，修复已被代码或生产指标证明的前端、SQL、应用层和导入热点，删除仍污染当前事实源的旧链，并完成 main 发布与生产只读验证。

</domain>

<decisions>
## Implementation Decisions

### 架构
- D-01 PostgreSQL canonical facts 继续作为业务事实源；普通页面保持 direct canonical query。
- D-02 Workbench active-generation 与 `workbench_relation` 是保留例外，不删除 worker/read model/freshness/version/atomic publish。
- D-03 禁止新增 Worker、页面 Read Model、Redis cache、Search projection、通用 Bootstrap API 或第三方压测框架。

### 性能
- D-04 先测量再优化；索引、普通列、cursor 和高基数筛选远程搜索只能由目标规模证据触发。
- D-05 页面首屏/API p95 目标保持 `<=1000ms`；写后可见性继续遵循现有 p99 `<=3000ms` 合同。
- D-06 精确 total、金额、统计、红冲、退款、关系和状态口径不得为性能降级。

### 关联台自收敛
- D-10 流水规则批量处理及其他普通页面写成功后只提交 canonical facts、version/audit，并刷新本页面；禁止向关联台做同步/异步页面 fan-out、operation barrier 或刷新目标通知。
- D-11 关联台 freshness/status 查询边界负责比较 source proof；发现 `stale` 时必须复用现有 `ReadModelRefreshGateway`，只 enqueue 已归一化、校验和去重后的精确 scope，由现有 Workbench worker 原子发布 active generation。
- D-12 关联台进入页面或重新获得焦点时立即检查；只要关联台页面可见，无论 `fresh/stale/refreshing`，每次 status 请求完成后等待 1 秒再发下一次。隐藏页面暂停，前端请求必须 single-flight；generation version 变化后只 reload 一次。
- D-13 禁止新增 endpoint、Worker、read model、数据库表/trigger、Redis、RabbitMQ 强依赖、跨页事件总线、BroadcastChannel、SSE 或第三方轮询依赖；每秒检查只允许调用现有有界 refresh-status，不得并发、积压或退化为重复完整 payload GET，并须以目标并发证明数据库/API 容量后才可发布。
- D-14 删除或继续保持删除已退休的普通写侧 Workbench refresh、operation barrier、targets 和 fallback；显式 maintenance/repair/rehydrate 以及独立 domain jobs 不属于页面 fan-out，不得误删。
- D-15 流水规则提交到关联台可见的生产合同保持 p99 `<=3000ms`；必须分别测量 canonical commit、status proof/enqueue、queue/worker publish 和浏览器 reload，不能用单个最快样本代替。
- D-16 该变更只能落在关联台查询/前端轮询边界；流水规则批量提交 API、事务、正式关系写入和本页 reload I/O 保持不变，其他页面的写/读合同不得被污染。
- D-17 所有会影响关联台结果的 canonical writer 必须推进关联台 exact-scope source proof；建立 writer→proof 覆盖矩阵和真实 PostgreSQL mutation contract test。发现漏项时只修 canonical version/`updated_at` 或 Workbench proof query，禁止恢复任何写侧 Workbench notification。

### 安全与发布
- D-07 目标规模数据只写隔离 performance/test 数据库；生产只做有界登录态 GET、health、dashboard、pg_stat 和现有 release gate。
- D-08 旧链删除必须先扫描 caller/consumer；无 hidden fallback、双读、旧 route alias 或退休 event 残留。
- D-09 每个根修复都有测试保护；全量回归通过后才 commit/push main、部署和生产验证。

</decisions>

<canonical_refs>
## Canonical References

- `AGENTS.md`
- `docs/architecture/module-boundaries/README.md`
- `docs/architecture/module-boundaries/inventory.md`
- `docs/architecture/module-boundaries/read-model-contracts.md`
- `docs/modules/finance-table-system/boundary-io.md`
- `docs/modules/pending-invoices/boundary-io.md`
- `docs/modules/input-invoice-usage/boundary-io.md`
- `docs/modules/output-invoice-collections/boundary-io.md`
- `docs/modules/reconciliation-workbench/boundary-io.md`
- `docs/modules/reconciliation-workbench/state-machine.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/bank-flow-rule-batches/boundary-io.md`
- `docs/modules/bank-flow-rule-batches/state-machine.md`
- `docs/modules/bank-flow-rule-batches/tests.md`
- `docs/modules/turnover-ledger/boundary-io.md`
- `docs/modules/cost-statistics/boundary-io.md`
- `docs/modules/imports-invoices/boundary-io.md`
- `docs/modules/imports-bank-transactions/boundary-io.md`
- `docs/modules/no-oa-bank-batches/boundary-io.md`
- `docs/modules/read-models/boundary-io.md`
- `docs/modules/runtime-workers/boundary-io.md`
- `docs/operations/monitoring.md`
- `docs/operations/runtime-worker-governance.md`
- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `backend/src/fin_ops_platform/services/workbench_query_freshness_service.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/bank_flow_rule_batch_application_service.py`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/pages/BankFlowRuleBatchPage.tsx`

</canonical_refs>

<deferred>
## Deferred Ideas

- 历史 projection 表物理 DROP 只在所有受支持 rollback release 均无 reader/writer/backlog 后另立 migration；本 Phase 只删除当前运行入口与旧事实描述。
- 若目标规模基准未证明 JSONB、索引或 cursor 必要，则不实施对应结构变更。

</deferred>
