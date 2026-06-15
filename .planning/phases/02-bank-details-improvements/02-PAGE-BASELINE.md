# 银行明细 L1.5 页面基线卡片

## Scope

- Phase: `02-bank-details-improvements`
- Page key: `bank-details`
- Route: `/bank-details`
- Page entry: `web/src/pages/BankDetailsPage.tsx`
- API client: `web/src/features/bankDetails/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/routes_bank_details.py`, `backend/src/fin_ops_platform/app/server.py` `/api/bank-details*`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

银行明细是银行流水事实、标签、no-OA 状态、业务对象关系和跨页刷新影响的核心页面。它读取银行明细和银行账户余额相关 read model，并为免 OA、外部往来、关联台、批量账务和成本链路提供上游事实。

当前页面需要重点识别：

1. 银行流水来自银行流水导入和后端标准化事实。
2. 标签、分类和业务对象关系会决定 no-OA、外部往来和关联候选的准入。
3. 页面不能把 stale 的银行明细 read model 展示成 fresh。
4. 修改标签/分类后应触发相关下游 dirty scopes，而不是只依赖前端事件。

## Cross-Page Dependencies

- Upstream:
  - `imports-bank-transactions`: 银行流水源事实。
  - `settings`: 账户、标签规则或系统配置可能影响展示和准入。
- Direct downstream:
  - `turnover-ledger`: 外部往来标签和三层分类。
  - `no-oa-bank-batches`: no-OA 标签准入和候选批次。
  - `reconciliation-workbench`: 银行流水参与匹配、候选和 active relation。
  - `batch-accounting`: 银行流水与 OA 行的批量账务关系。
  - `cost-statistics`: 银行流水分类和关系影响成本聚合。
- Indirect downstream:
  - `tax-offset`
  - `pending-invoices`
  - `app-health-operations`
- Phase 0 dependency group: `Workbench relation core`，并且是多个 bank-derived 页面事实入口。

## Read Model / Worker / App Status

- Read models: `bank_detail`, `bank_account_balance`
- Workers: `bank-detail`, `bank-account-balance`
- Likely dirty scopes: 按月份、账户、全局或页面查询条件，具体以 registry 为准。
- Related read models: `turnover_ledger`, `no_oa_bank_batch`, `workbench`, `workbench_relation`, `cost_statistics`
- Freshness rule: 银行明细标签/分类变更后，下游页面 fresh 之前不能用本地事件伪造跨页一致性。

## Current Gaps To Assess Before L2

- 页面完善目标是筛选/分页/导出、标签编辑、分类规则、账户余额、详情 drawer，还是跨页刷新。
- 标签/分类变更是否有明确的 API contract、审计字段、版本冲突和 downstream dirty scopes。
- 页面是否展示 read model stale/refreshing/missing 诊断，而不是把空列表误认为无数据。
- 与 no-OA、外部往来、关联台的候选准入规则是否在 UI 和后端一致。
- 是否存在旧标签或旧分类逻辑绕过当前服务边界；L2 必须先识别再决定移除。

## Risks

- 权限: 查看银行流水、编辑标签/分类、导出、查看敏感账户信息需要权限分层。
- 审计: 标签/分类变更、批量操作、导出和账户映射变更需要可追溯。
- stale/fresh: 银行明细是多页面上游，stale 会级联污染下游判断。
- 跨页刷新: no-OA、外部往来、关联台、批量账务、成本统计都可能被影响。
- worker: `bank-detail` 和 `bank-account-balance` refresh 失败会影响列表和余额口径。
- 导出: 导出字段、筛选条件、金额符号和账户信息需要回归。
- 历史数据: 旧标签、旧分类、已提交 no-OA/turnover relation 不能被简单重算覆盖。

## Test Entry Points

- Backend:
  - `tests/test_bank_details_*`
  - `tests/test_bankdetail_*`
  - bank detail read model、tag/category service、account balance 相关测试
- Frontend:
  - `web/src/test/BankDetails*.test.tsx`
- Integration candidates:
  - 银行流水导入 -> bank detail fresh -> 标签/分类变更 -> no-OA/turnover/workbench dirty refresh
  - stale bank detail -> 页面诊断 -> refresh 后恢复列表

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖标签/分类准入、金额方向、重复流水、版本冲突。
- Service-layer tests: 适用。覆盖 bank detail service、账户余额、审计、dirty scope fan-out。
- API contract tests: 适用。覆盖列表、详情、标签/分类更新、导出、权限和 stale/status 字段。
- Read model/cache/background job tests: 适用。覆盖 `bank_detail`、`bank_account_balance` worker 和 freshness。
- Frontend component/interaction tests: 适用。覆盖筛选、排序、分页、加载/空/错/stale、编辑、导出。
- End-to-end business-flow integration tests: 适用。银行导入到银行明细再到下游候选是关键路径。
- Existing feature regression tests: 适用。保护 no-OA、外部往来、关联台、成本统计和旧导出。

## Docs Impact Entry

- Module docs: `docs/modules/bank-details/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/bank-turnover-and-no-oa.md`
  - `docs/app-architecture/pages.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 若变更标签/分类业务口径，必须同步产品规格；若只调整 UI 展示且契约不变，可在最终说明 docs 不适用。

## Legacy / Transitional Paths

- 不得新增绕过银行明细服务边界的标签/分类写入。
- 旧标签、旧分类或旧候选准入逻辑如仍存在，L2 要标出调用点和删除/迁移计划。
- 下游页面不能复制银行明细分类规则；应依赖明确服务/API/read model。

## L2 Questions

- 银行明细本轮最需要完善的是用户体验、标签规则、导出、详情，还是作为上游事实的 refresh 正确性？
- 标签/分类变更是否允许批量提交；需要哪些 expected version 或幂等键？
- 下游 dirty scopes 是立即 enqueue 还是由 lifecycle worker 聚合？
- 历史已提交 no-OA/turnover relation 遇到分类漂移时是否需要 repair 流程？
- 是否要先删除某条旧分类或旧标签路径，避免双写/双口径？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确银行明细事实源、标签/分类 contract、下游影响、旧逻辑删除、测试矩阵和文档影响。
