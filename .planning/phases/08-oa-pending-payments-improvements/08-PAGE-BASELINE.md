# OA 待付款核对 L1.5 页面基线卡片

## Scope

- Phase: `08-oa-pending-payments-improvements`
- Page key: `oa-pending-payments`
- Route: `/oa-pending-payments`
- Page entry: `web/src/pages/OaPendingPaymentsPage.tsx`
- API client: `web/src/features/oaPendingPayments/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`, `backend/src/fin_ops_platform/app/server.py` `/api/oa-pending-payments*`
- Core services: `oa_pending_payment_service.py`, `oa_pending_payment_read_model_service.py`, `oa_pending_payment_read_model_details.py`, `invoice_usage_collection_sql_projection.py`, `invoice_usage_collection_read_model_refresh.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

OA 待付款核对关注 OA 单据、支出银行流水、进项发票、Workbench relation、SQL read model、invoice lifecycle 分发、详情 drawer 和异常反馈。页面以 OA 申请为主行，`paymentStatus` 由 `InvoiceLifecyclePolicy` 或等价 lifecycle read boundary 判定，页面不得自行定义付款状态。

当前关键边界：

1. 生产读路径必须先经过 `OaPendingPaymentReadModelService` 的 freshness/source-version gate。
2. rows、filter-options、OA detail、bank detail、invoice detail、relation detail 在 read model missing/stale/source mismatch 时只能返回 refreshing/unavailable 并入队 refresh。
3. 不允许同步 live scan 旧事实并伪装 fresh。
4. OA 同步和 invoice usage collection 共同影响本页数据可见性。

## Cross-Page Dependencies

- Upstream:
  - OA integration / OA sync
  - `imports-invoices`
  - `imports-bank-transactions`
  - `reconciliation-workbench`
  - `pending-invoices`
  - `input-invoice-usage`
- Downstream:
  - `cost-statistics`
  - `tax-offset`
  - `app-health-operations`
- Phase 0 dependency group: `Invoice lifecycle and tax`，并依赖 OA integration。

## Read Model / Worker / App Status

- Read models: `oa_pending_payment`, `invoice_lifecycle`
- Workers: `invoice-usage-collection`, `oa-sync`
- Related source versions: invoice usage collection source versions, OA projection sync
- Related read model: `workbench_relation`
- Freshness rule: 本页详情和列表必须使用 read model gate；missing/stale/source mismatch 返回 refreshing/unavailable，不得 fallback 到旧 live scan。

## Current Gaps To Assess Before L2

- 用户要完善的是列表筛选、详情 drawer、异常反馈、OA 同步诊断，还是付款状态展示。
- filter-options 和详情接口是否都遵循同一 freshness/source-version gate。
- OA detail、bank detail、invoice detail unavailable 时的 UI 是否可理解。
- `paymentStatus` 是否完全来自 lifecycle boundary。
- 是否存在旧 live scan fallback 或页面私有状态判断；L2 必须移除或封堵。

## Risks

- 权限: 查看 OA 单据、银行/发票详情、关系详情和导出需要权限校验。
- 审计: 异常反馈、导出、OA 数据访问和详情查看可能需要审计。
- stale/fresh: OA projection、invoice lifecycle、workbench relation 和本页 read model 状态不同步会误导付款判断。
- 跨页刷新: 待找发票、进项使用、关联台、成本统计和税金抵扣都可能影响本页。
- worker: `oa-sync` 或 `invoice-usage-collection` 失败会导致 read model source mismatch。
- 导出: OA 主行、付款状态、关联发票/银行流水字段需要回归。
- 历史数据: 旧 OA projection 或旧 relation snapshot 不能被同步 live scan 当作 fresh。

## Test Entry Points

- Backend:
  - `tests/test_oa_pending_payment_*`
  - OA pending payment read model/details、invoice usage collection、OA sync 相关测试
- Frontend:
  - `web/src/test/OaPendingPaymentsPage.test.tsx`
- Integration candidates:
  - OA sync -> invoice usage collection refresh -> OA pending payment fresh -> detail 可用
  - read model stale/source mismatch -> detail unavailable -> refresh enqueue

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖付款状态、OA 主行聚合、详情 unavailable 语义和异常反馈规则。
- Service-layer tests: 适用。覆盖 read model gate、details service、OA sync/source versions、audit。
- API contract tests: 适用。覆盖 rows、filter-options、detail APIs、权限、refreshing/unavailable response。
- Read model/cache/background job tests: 适用。覆盖 `oa_pending_payment`、`invoice_lifecycle`、`invoice-usage-collection`、`oa-sync`。
- Frontend component/interaction tests: 适用。覆盖筛选、详情 drawer、loading/empty/error/stale/unavailable。
- End-to-end business-flow integration tests: 适用。保护 OA 同步到付款核对页面可见的关键路径。
- Existing feature regression tests: 适用。保护进项使用、待找发票、关联台、税金抵扣和旧详情行为。

## Docs Impact Entry

- Module docs: `docs/modules/oa-pending-payments/`
- Long-term docs likely affected when behavior changes:
  - `docs/architecture/oa-integration.md`
  - `docs/product-specs/invoice-lifecycle.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 涉及 OA sync、read model gate、详情 API 或状态口径时必须同步长期文档。

## Legacy / Transitional Paths

- 不得在 rows/filter-options/detail 请求中同步 live scan 旧事实并伪装 fresh。
- 页面不得私有定义 `paymentStatus`。
- 旧 OA projection 或旧 relation snapshot fallback 如存在，L2 必须标明删除路径。

## L2 Questions

- 本轮完善目标是列表体验、详情 drawer、OA 同步诊断，还是付款状态口径？
- unavailable 和 refreshing 在前端是否需要不同视觉和操作入口？
- OA sync source mismatch 是否阻断所有详情，还是只阻断受影响字段？
- 是否存在旧 live scan fallback 需要先删除？
- 导出是否允许在 stale/source mismatch 下执行？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确 OA/read model gate、invoice lifecycle、权限审计、旧逻辑删除、测试矩阵和文档影响。
