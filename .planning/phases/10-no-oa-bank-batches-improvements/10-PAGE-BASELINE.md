# 免 OA 流水批量处理 L1.5 页面基线卡片

## Scope

- Phase: `10-no-oa-bank-batches-improvements`
- Page key: `no-oa-bank-batches`
- Route: `/no-oa-bank-batches`
- Page entry: `web/src/pages/NoOaBankBatchPage.tsx`
- API client: `web/src/features/noOaBankBatches/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- Core services: `no_oa_bank_batch_application_service.py`, `no_oa_bank_batch_service.py`, `no_oa_bank_batch_tag_selection_service.py`, `no_oa_bank_batch_read_model_refresh.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

免 OA 流水批量处理负责没有 OA 单据但仍需业务处理的银行流水批次。它是 Bankdetail 高风险子域，不是独立事实源。候选来源是银行明细有效分类和免 OA 标签准入，未提交候选必须排除已被 Workbench active relation 占用的流水。

当前关键边界：

1. `GET /api/no-oa-bank-batches` 优先读 `no_oa_bank_batch` SQL read model；missing/stale 时只 enqueue refresh，不在 GET 热路径同步重建。
2. `submit-selection` 只提交用户当前选择的流水，要求同月、同银行账户、同 `category_code`，且 code 在当前免 OA 标签准入范围内。
3. submit、withdraw、legacy migration、repair、category drift cleanup 都必须通过 `WorkbenchRelationCommandService` 写入或撤销 `relation_mode=no_oa_bank_batch`。
4. `save_no_oa_bank_batches` 写入当前完整 no-OA snapshot；缺席于新 snapshot 的旧 draft/conflict/submitted row 必须移除。
5. 前端写操作必须接入 `GlobalOperationOverlayProvider`，等待 `no_oa_bank_batch` operation barrier fresh 后重载。

## Cross-Page Dependencies

- Upstream:
  - `bank-details`: 有效分类、免 OA 标签准入、银行流水事实。
  - `imports-bank-transactions`: 银行流水源事实。
  - `reconciliation-workbench`: active relation 占用判断。
- Downstream:
  - `reconciliation-workbench`: no-OA submit 写入 Workbench active relation。
  - `batch-accounting`: 共享 Workbench relation 和银行流水占用边界。
  - `turnover-ledger`: 分类/标签边界相邻，不能互相污染。
  - `cost-statistics`: no-OA 批次可能影响成本聚合。
- Phase 0 dependency group: `Workbench relation core`。

## Read Model / Worker / App Status

- Read model: `no_oa_bank_batch`
- Worker: `no-oa-bank-batch`
- Job type: `no_oa_bank_batch.read_model.refresh`
- Related read model: `workbench_relation`
- App Status domain: `no_oa_bank_batches`
- Freshness rule: `workbench_relation` distribution non-fresh 只影响读侧候选和诊断；写操作由 command service 的 canonical relation、idempotency、owner 状态、权限/session 和 DB 可写性决定。

## Current Gaps To Assess Before L2

- 用户要完善的是标签准入、候选展示、批量提交、撤回、冲突处理、历史迁移还是刷新状态。
- 页面是否区分 missing/stale read model 和真实空列表。
- tag-selection 是否仍只读取银行明细自动标签规则中的可用标签，不保存第三层外部往来分类字段。
- no-OA 与 internal transfer 在关联台和本页面提交时是否收敛到同一 submitted batch / active relation。
- 旧 manual_confirmed relation repair/迁移是否仍存在；L2 必须明确是否继续保留。

## Risks

- 权限: 标签准入、提交、撤回、修复、查看批次和导出需要权限边界。
- 审计: tag-selection、submit-selection、single submit、withdraw、legacy repair 都必须可追溯。
- stale/fresh: stale snapshot 不能导致重复提交、候选污染或撤回错误。
- 跨页刷新: Workbench relation、银行明细、成本统计、搜索和前端刷新提示都受影响。
- worker: `no-oa-bank-batch` worker 不得执行 relation repair 或 pair relation 持久化。
- 导出: 如存在批次导出或错误导出，字段和状态口径需保护。
- 历史数据: submitted no-OA batch 是 cleanup 闭环占用证据，不能被旧自动 decision 再污染。

## Test Entry Points

- Backend:
  - `tests/test_no_oa_bank_batch_*`
  - tag selection、submit/withdraw、read model refresh、legacy migration/repair 相关测试
- Frontend:
  - `web/src/test/NoOaBankBatch*.test.tsx`
- Integration candidates:
  - 银行分类 -> no-OA 候选 -> submit -> Workbench relation fresh -> withdraw
  - internal transfer 先在关联台提交或先在 no-OA 提交都收敛到同一 relation

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖标签准入、同月/同账户/category 约束、internal transfer、撤回合法性。
- Service-layer tests: 适用。覆盖 application service、read model refresh、command service 委托、repair/cleanup。
- API contract tests: 适用。覆盖列表、tag-selection、submit-selection、submit、withdraw、权限和 stale/status。
- Read model/cache/background job tests: 适用。覆盖 `no_oa_bank_batch` worker、snapshot 保存和 operation barrier。
- Frontend component/interaction tests: 适用。覆盖候选选择、标签保存、提交/撤回、stale/empty/error、overlay。
- End-to-end business-flow integration tests: 适用。保护 no-OA 提交到关联台关系的关键路径。
- Existing feature regression tests: 适用。保护银行明细、关联台、外部往来、成本统计和旧 repair 行为。

## Docs Impact Entry

- Module docs: `docs/modules/no-oa-bank-batches/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/bank-turnover-and-no-oa.md`
  - `docs/operations/object-identity-dedup.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 涉及 relation repair、分类漂移或 internal transfer 口径时必须同步长期文档。

## Legacy / Transitional Paths

- legacy migration、submitted repair、category drift cleanup 必须只负责识别修复意图并委托 command service。
- `no_oa_bank_batch.read_model.refresh` worker 不得执行 relation repair 或 pair relation 持久化。
- 不得把第三层外部往来分类字段保存进 no-OA tag-selection。
- GET 路径不得同步重建批次或执行 legacy relation repair。

## L2 Questions

- 本轮完善的目标是候选准确性、批量提交体验、撤回、标签准入，还是历史 repair 清理？
- 是否存在必须移除的旧 direct pair mutation 或 GET-path repair？
- 读侧 non-fresh 时页面允许哪些操作，哪些必须阻断？
- internal transfer 与 no-OA 收敛是否需要单独 integration test？
- tag-selection 保存后哪些 downstream scopes 必须 refresh？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确 no-OA 状态机、relation command 边界、read model/worker、权限审计、旧逻辑删除、测试矩阵和文档影响。
