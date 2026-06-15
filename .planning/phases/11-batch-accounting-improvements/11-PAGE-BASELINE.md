# 批量账务 L1.5 页面基线卡片

## Scope

- Phase: `11-batch-accounting-improvements`
- Page key: `batch-accounting`
- Route: `/batch-accounting`
- Page entry: `web/src/pages/BatchAccountingPage.tsx`
- API client: `web/src/features/batchAccounting/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/server.py` `/api/batch-accounting*`
- Core services: `batch_accounting_service.py`, `workbench_relation_read_facade.py`, `workbench_relation_read_model_refresh.py`, `derived_data_lifecycle_service.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

批量账务页面用于把符合批量账务条件的银行流水与日常报销 OA 行做人工关系确认，并支持已确认关系撤回。它不是独立事实源，银行流水、OA 行和已有关联关系来自 Workbench / Workbench relation read model。

当前关键边界：

1. `GET /api/batch-accounting` 必须返回 `summary`、`bank_rows`、`oa_rows`、`relations_by_bank_row_id`、`read_model_status`、`read_model_stale_reasons`、`read_model_scope_keys`、`refresh_enqueued`。
2. submit 必须通过 `WorkbenchRelationCommandService.confirm_relation(...)` 写入，`special_metadata.source=batch_accounting`。
3. withdraw 只能撤回当前 active 的批量账务关系，并保留提交/撤回历史备注。
4. GET 读取 relation 必须通过 relation read facade/freshness 边界请求 `require_fresh`，不能同步 rebuild 或直接写 durable queue。
5. 前端 submit/withdraw 成功后等待 `workbench_relation` operation barrier 对 affected months fresh，再重载 payload。

## Cross-Page Dependencies

- Upstream:
  - `reconciliation-workbench`: Workbench relation/read model。
  - `bank-details`: 银行流水事实、标签和分类。
  - OA 行事实和 OA 同步链路。
- Downstream:
  - `reconciliation-workbench`: batch relation 是 Workbench active relation 的一类来源。
  - `cost-statistics`: 批量账务关系可能影响成本归属。
  - `pending-invoices`、`input-invoice-usage`、`output-invoice-collections`、`oa-pending-payments`: relation 变化可能影响发票生命周期或关系标签。
  - `app-health-operations`: worker/read model 状态观测。
- Phase 0 dependency group: `Workbench relation core`。

## Read Model / Worker / App Status

- Read model: `workbench_relation`
- Worker: `workbench-relation`
- Job type: `workbench_relation.read_model.refresh`
- Related services: `DerivedDataLifecycleService`, relation distribution mapper/projection
- Freshness rule: `read_model_status !== "fresh"` 时，页面可以展示可用 payload 和诊断，但不能把非 fresh 空关系当成真实未提交；写入阻断应由 canonical relation、权限/session、DB 可写性、idempotency 和 owner 状态决定。

## Current Gaps To Assess Before L2

- 用户要完善的是候选筛选、提交/撤回、差额说明、stale 诊断、历史备注，还是跨页刷新。
- API 是否完整透出 read model 状态和 stale reasons。
- 前端是否仍依赖 `workbenchRelationUpdated` 事件作为事实源；应仅作为同浏览器刷新提示。
- `repair_legacy_case_id_collisions(...)` 是否仍需要；如保留必须通过 command service。
- GET 路径是否存在 legacy repair 或写入副作用；L2 必须确认并移除。

## Risks

- 权限: 查看候选、提交、撤回、查看历史备注需要权限/session 校验。
- 审计: 提交、撤回、repair 和备注变更需要记录操作者和原因。
- stale/fresh: 非 fresh relation 不能被解释为无关系；operation barrier 不能由本地事件替代。
- 跨页刷新: 关系变更影响关联台、银行明细、成本统计、搜索和发票生命周期相关页面。
- worker: `workbench-relation` refresh 失败会导致页面候选和已提交状态不可信。
- 导出: 如涉及批量账务导出，字段和关系状态需回归。
- 历史数据: OA 附件 `case_id` / `existing_case` 显示归属不得被恢复为 active relation。

## Test Entry Points

- Backend:
  - `tests/test_batch_accounting_api.py`
  - batch service、relation facade、repair、derived lifecycle 相关测试
- Frontend:
  - `web/src/test/BatchAccountingPage.test.tsx`
- Integration candidates:
  - batch submit -> `workbench_relation` fresh -> 关联台显示 relation
  - withdraw -> 只撤回当前 active batch relation -> 历史备注保留

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖候选条件、submit/withdraw 约束、existing_case 不恢复、备注规则。
- Service-layer tests: 适用。覆盖 batch service、command service 委托、relation facade、legacy repair。
- API contract tests: 适用。覆盖 GET response shape、submit/withdraw 成功/错误/权限/stale 字段。
- Read model/cache/background job tests: 适用。覆盖 `workbench_relation` refresh、operation barrier 和 stale 诊断。
- Frontend component/interaction tests: 适用。覆盖 loading/empty/error/stale、筛选、提交、撤回、事件回归。
- End-to-end business-flow integration tests: 适用。保护批量账务关系写入到关联台可见的关键路径。
- Existing feature regression tests: 适用。保护关联台、银行明细、成本统计、发票链路和旧 relation 展示。

## Docs Impact Entry

- Module docs: `docs/modules/batch-accounting/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/reconciliation-and-workbench.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/app-architecture/pages.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 涉及 API DTO、operation barrier、relation repair 或 relation semantics 时必须同步长期文档。

## Legacy / Transitional Paths

- submit/withdraw/repair 缺 command service 时必须 fail fast，不得 direct pair mutation。
- GET 必须只读，不能在列表读取路径执行 legacy relation repair。
- 前端 `workbenchRelationUpdated` 不是跨页面一致性事实源。
- 旧 repair 如继续保留，必须由明确 repair 边界触发，并有测试保护。

## L2 Questions

- 本轮完善目标是候选准确性、提交/撤回体验、stale 状态展示，还是 legacy repair 清理？
- GET response shape 是否需要扩展；若扩展，哪些前端 mapper 和测试受影响？
- relation non-fresh 时允许哪些写操作，哪些由 command service 阻断？
- 是否必须先移除 GET-path repair 或 direct pair fallback？
- 下游页面刷新失败时，批量账务页面如何显示诊断和恢复入口？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确 relation read/write contract、read model/worker、权限审计、旧逻辑删除、测试矩阵和文档影响。
