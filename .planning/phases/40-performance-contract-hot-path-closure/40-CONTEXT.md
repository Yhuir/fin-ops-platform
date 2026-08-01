# Phase 40: 性能合同与核心热路径闭环 - Context

**Gathered:** 2026-08-01
**Status:** Ready for execution
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
- `docs/modules/turnover-ledger/boundary-io.md`
- `docs/modules/cost-statistics/boundary-io.md`
- `docs/modules/imports-invoices/boundary-io.md`
- `docs/modules/imports-bank-transactions/boundary-io.md`
- `docs/modules/no-oa-bank-batches/boundary-io.md`
- `docs/modules/read-models/boundary-io.md`
- `docs/modules/runtime-workers/boundary-io.md`
- `docs/operations/monitoring.md`
- `docs/operations/runtime-worker-governance.md`

</canonical_refs>

<deferred>
## Deferred Ideas

- 历史 projection 表物理 DROP 只在所有受支持 rollback release 均无 reader/writer/backlog 后另立 migration；本 Phase 只删除当前运行入口与旧事实描述。
- 若目标规模基准未证明 JSONB、索引或 cursor 必要，则不实施对应结构变更。

</deferred>

