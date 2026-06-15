# 成本统计 L1.5 页面基线卡片

## Scope

- Phase: `05-cost-statistics-improvements`
- Page key: `cost-statistics`
- Route: `/cost-statistics`
- Page entry: `web/src/pages/CostStatisticsPage.tsx`
- API client: `web/src/features/cost-statistics/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/routes_cost_statistics.py`, `backend/src/fin_ops_platform/app/server.py` `/api/cost-statistics*`
- Core services: cost statistics projection/read model/export services, cost/tax lifecycle integration
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

成本统计关注项目范围、费用归因、导出 shape 和 cost read model freshness。它是多个源事实和关系状态的汇总页面，不应定义新的业务事实源。

当前关键边界：

1. 成本统计 read model refresh scope 必须是 `active:YYYY-MM`、`all:YYYY-MM`、`active:all` 或 `all:all`。
2. 旧裸月份/裸 `all` 只能在统一 read model refresh scope gateway 中归一化，不能直接进入 durable queue。
3. 生产刷新由专用 `cost-statistics` RabbitMQ consumer 承担；旧 `cost-tax` combined worker 只作为兼容消费者。
4. `cost_statistics` freshness 以 PostgreSQL dirty scope/outbox/readiness 为事实源。

## Cross-Page Dependencies

- Upstream:
  - `imports-bank-transactions`
  - `imports-invoices`
  - `imports-etc-invoices`
  - `reconciliation-workbench`
  - `bank-details`
  - `tax-offset`
  - `input-invoice-usage`
  - `output-invoice-collections`
  - `settings` 项目范围
- Downstream:
  - `app-health-operations`
  - 导出/管理报表使用者
- Phase 0 dependency group: `Analytics and status`，同时依赖 `Invoice lifecycle and tax`、`Workbench relation core` 和 `ETC chain`。

## Read Model / Worker / App Status

- Read model: `cost_statistics`
- Worker: `cost-statistics`
- Compatibility worker: `cost-tax`
- Valid scopes: `active:YYYY-MM`, `all:YYYY-MM`, `active:all`, `all:all`
- Freshness rule: 页面不能读取旧 read model 却展示为 fresh；任何 enqueue 必须经过 scope gateway normalize/validate/dedupe。

## Current Gaps To Assess Before L2

- 用户要完善的是项目范围、费用归因、筛选/导出、汇总维度，还是 freshness/status。
- 是否仍有裸月份/裸 `all` 直接进入 durable queue 的旧路径。
- 导出 shape 是否与页面筛选、项目范围和 read model source version 绑定。
- 页面是否区分 refreshing/stale/missing 和真实空数据。
- `cost-tax` 兼容 worker 是否在文档/UI/诊断中造成主刷新 lane 混淆。

## Risks

- 权限: 查看成本、导出、项目范围相关筛选需要权限控制。
- 审计: 导出、项目范围变更和手工归因调整如存在需记录。
- stale/fresh: 上游 relation、发票 lifecycle、税务、ETC 和项目范围变化都会影响成本结果。
- 跨页刷新: 设置、银行明细、关联台、税金抵扣、ETC 和发票链路都会 fan-out 到成本统计。
- worker: `cost-statistics` worker backlog 或 `cost-tax` 兼容误用会导致 SLO 失真。
- 导出: 字段、排序、金额汇总、项目范围和空值处理需要回归。
- 历史数据: 旧 scope 残留需要受控清理，不能在业务请求里隐式修复。

## Test Entry Points

- Backend:
  - `tests/test_cost_statistics_*`
  - cost read model、scope gateway、export、worker readiness 相关测试
- Frontend:
  - `web/src/test/CostStatistics*.test.ts`
- Integration candidates:
  - 上游发票/关系/项目范围变化 -> cost dirty scope -> worker refresh -> 页面 fresh
  - 裸 scope 输入 -> gateway 归一化或拒绝 -> durable queue 不出现非法 scope

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖费用归因、项目范围、汇总维度、金额边界。
- Service-layer tests: 适用。覆盖 read model refresh、scope gateway、export、source versions。
- API contract tests: 适用。覆盖列表/汇总/导出 response shape、权限、stale/status。
- Read model/cache/background job tests: 适用。覆盖 `cost_statistics` worker、dirty scope/outbox/readiness 和非法 scope。
- Frontend component/interaction tests: 适用。覆盖筛选、汇总、导出、loading/empty/error/stale。
- End-to-end business-flow integration tests: 适用。保护上游关系或发票变化到成本统计可见的关键路径。
- Existing feature regression tests: 适用。保护税金抵扣、关联台、ETC、设置和旧导出 shape。

## Docs Impact Entry

- Module docs: `docs/modules/cost-statistics/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/cost-tax.md`
  - `docs/app-architecture/pages.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 涉及 scope contract、worker lane、导出 shape 或成本口径时必须同步长期文档。

## Legacy / Transitional Paths

- 裸月份/裸 `all` 只能在 scope gateway 归一化，不能直接进入 durable queue。
- `cost-tax` combined worker 是兼容消费者，不应作为新增能力唯一 lane。
- 生产残留裸 scope 使用 `scripts/check-read-model-scope-contracts.py` 检查和受控清理，不在页面请求中隐式修复。

## L2 Questions

- 本轮完善目标是成本口径、项目范围、导出，还是 worker/freshness 可见性？
- 是否存在直接 enqueue 裸 scope 的旧调用点必须先删除？
- 导出是否要绑定 source versions 或 read model status？
- 上游 source stale 时页面是否允许导出？
- `cost-tax` 兼容消费者是否需要在 App Status 或文档中降噪？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确成本口径、scope contract、read model/worker、权限审计、旧逻辑删除、测试矩阵和文档影响。
