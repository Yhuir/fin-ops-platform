# 关联台 L1.5 页面基线卡片

## Scope

- Phase: `04-reconciliation-workbench-improvements`
- Page key: `reconciliation-workbench`
- Route: `/`
- Page entry: `web/src/pages/ReconciliationWorkbenchPage.tsx`
- API client: `web/src/features/workbench/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/server.py` `/api/workbench*`, `backend/src/fin_ops_platform/app/routes_workbench.py`
- Core services: `WorkbenchRelationCommandService`, `WorkbenchQueryFacade`, `WorkbenchPairRelationService`, workbench read model/projection services
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

关联台是 OA、银行流水、发票跨页面关系的核心操作台。它保留 active generation 原子发布模型，不应被机械改造成普通 read model gateway。`app.workbench_pair_relations` 中的 active relation 是已配对事实源；页面只能消费 active generation 发布后的真实 group，不做前端本地自动配对。

当前关键边界：

1. active pair relation 是唯一已配对事实；同一 row 不能同时属于两个不同 active case。
2. `GET /api/workbench/rows/{row_id}` 是只读 row detail，优先 live service/cache，miss 后经 `WorkbenchQueryFacade` 读 SQL active generation。
3. `confirm-link`、`cancel-link`、`withdraw-link` 必须通过 `WorkbenchRelationCommandService` 写入；缺 command service 时 fail fast。
4. 选择上下文以 group 为单位；已配对区与未配对区的操作语义不同。
5. 写操作成功后，前端只能等待后端返回的 operation freshness targets 并应用后端 projection，不能用本地 optimistic 重排伪造结果。

## Cross-Page Dependencies

- Upstream:
  - `imports-bank-transactions`
  - `imports-invoices`
  - `bank-details`
  - 发票生命周期相关页面和 OA 同步事实
- Direct related pages:
  - `batch-accounting`
  - `no-oa-bank-batches`
  - `turnover-ledger`
  - `pending-invoices`
  - `input-invoice-usage`
  - `oa-pending-payments`
  - `output-invoice-collections`
  - `tax-offset`
  - `cost-statistics`
- Phase 0 dependency group: `Workbench relation core`。

## Read Model / Worker / App Status

- Read models: `workbench`, `workbench_relation`
- Workers: `workbench`, `workbench-relation`, `workbench-matching`
- Matching dirty source: `job.workbench_matching_dirty_scopes`
- Active generation: `workbench` all/month shard 原子发布模型
- Freshness rule: `workbench` month shard、`workbench:all`、`workbench_relation` 和跨页面 downstream 可以有不同 SLO；写 overlay 释放条件只能使用后端返回的 operation targets。

## Current Gaps To Assess Before L2

- 用户要完善的是匹配/撤回/拆分、详情 drawer、筛选搜索、异常处理、刷新状态，还是跨页一致性。
- 当前前端是否仍有本地 optimistic paired/open 重排或伪造 group 结果。
- 撤回 preview/submit 是否完整携带 `operation_type`、`preview_id`、`submit_expected_versions`。
- `restorable_on_withdraw`、`existing_case` 和 history 恢复边界是否在 API/UI 中清晰。
- 旧 `WorkbenchPairRelationService` direct mutation 调用点是否仍存在；L2 必须明确清理或隔离。

## Risks

- 权限: 查看、确认关联、撤回、拆分、异常处理、详情读取需要权限和 session 校验。
- 审计: 所有关联写入、撤回、异常闭环、自动候选和规则版本必须可追溯。
- stale/fresh: active generation、relation distribution 和 matching rules source versions 必须正确传播。
- 跨页刷新: 关联变化影响多数业务页面和 read model。
- worker: `workbench`、`workbench-relation`、`workbench-matching` 任一失败都会影响页面可信度。
- 导出: 如涉及导出或批量操作，必须保护 group 展示和字段口径。
- 历史数据: 历史污染 relation、旧 `case_id`、旧 attachment cache 不能被恢复为 active relation。

## Test Entry Points

- Backend:
  - `tests/test_workbench_*`
  - relation command、withdraw preview/submit、active generation、matching worker 相关测试
- Frontend:
  - `web/src/test/Workbench*.test.tsx`
- Integration candidates:
  - confirm relation -> operation targets fresh -> paired group 更新 -> 下游页面刷新
  - withdraw relation -> only restorable history restored -> stale/inconsistent owner 不污染 active relation

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖匹配规则、row 去重、撤回恢复、operation projection、规则版本。
- Service-layer tests: 适用。覆盖 command service、query facade、active generation、matching worker、audit。
- API contract tests: 适用。覆盖 rows detail、confirm/cancel/withdraw、preview/submit、错误和权限。
- Read model/cache/background job tests: 适用。覆盖 `workbench`、`workbench_relation`、`workbench-matching` freshness。
- Frontend component/interaction tests: 适用。覆盖 loading/empty/error/stale、group selection、confirm、withdraw、split、overlay。
- End-to-end business-flow integration tests: 适用。关联台是跨模块核心，至少保护一条确认与撤回全链路。
- Existing feature regression tests: 适用。保护下游页面、旧 row detail、旧匹配规则、旧 relation 展示和权限。

## Docs Impact Entry

- Module docs: `docs/modules/reconciliation-workbench/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/reconciliation-and-workbench.md`
  - `docs/app-architecture/pages.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 关联台变更通常高概率需要同步长期架构或 API 文档。

## Legacy / Transitional Paths

- 缺 command service 时不得回退到 `WorkbenchPairRelationService` 直接写 pair snapshot。
- Payload build/repair 过程不得直接 mutate pair relation service。
- 前端 domain event 只提示同浏览器刷新，不是事实源。
- 任何旧 relation repair 或 legacy mutation 必须从 GET/read 路径移除，迁到明确 command/repair 边界。

## L2 Questions

- 本轮完善的入口是普通确认、统一撤回/拆分、异常处理、详情，还是匹配规则 freshness？
- 哪些旧路径仍直接写 pair relation；是否必须先删除这些旧路径再开发新功能？
- 写 overlay 的 release target 是否需要按操作类型区分？
- all-scope 聚合、month shard 和 relation distribution 的 stale 如何在 UI 呈现？
- 下游页面刷新失败时，关联台是否只显示诊断，还是阻断特定写入？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确 relation command 边界、active generation、worker/read model、权限审计、旧逻辑删除、测试矩阵和文档影响。
