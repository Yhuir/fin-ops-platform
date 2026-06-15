# 销项发票收款情况 L1.5 页面基线卡片

## Scope

- Phase: `09-output-invoice-collections-improvements`
- Page key: `output-invoice-collections`
- Route: `/output-invoice-collections`
- Page entry: `web/src/pages/OutputInvoiceCollectionsPage.tsx`
- API client: `web/src/features/outputInvoiceCollections/api.ts`
- Backend entrypoints: `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`, `backend/src/fin_ops_platform/app/server.py` `/api/output-invoice-collections*`
- Core services: `output_invoice_collection_service.py`, `output_invoice_collection_lifecycle_service.py`, `output_invoice_collection_receipt_service.py`, `output_invoice_collection_status_service.py`, `invoice_lifecycle_policy.py`
- Phase 0 refs:
  - `.planning/phases/00-cross-page-dependency-baseline/PAGE-DEPENDENCY-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/READ-MODEL-WORKER-MATRIX.md`
  - `.planning/phases/00-cross-page-dependency-baseline/CROSS-PAGE-DATAFLOW.md`
  - `.planning/phases/00-cross-page-dependency-baseline/LEGACY-ENTRYPOINTS.md`

## Page Current State

销项发票收款情况维护列表、筛选、排序、分页、详情 drawer、收款状态、提醒、红蓝票关系和正式收据生命周期。列表读接口优先读取 SQL read model `output_invoice_collection`；miss/stale/schema/source version mismatch 时返回 `202` 与 `read_model_status=refreshing`，不得在请求线程同步 live rebuild。

当前关键边界：

1. fresh SQL rows 返回前叠加 lifecycle facts：`collectionStatus`、手动状态、提醒、红蓝票关系和正式收据摘要。
2. 收款状态规则由 `InvoiceLifecyclePolicy` 与 `OutputInvoiceCollectionStatusRuleService` 统一判定。
3. 写接口只通过 lifecycle service 与 receipt service 写 lifecycle facts；service 不读取 HTTP header/cookie。
4. 手动状态、提醒、红蓝票关系、收据 create/void/reissue 必须 enqueue `output_invoice_collection` scope，并在 PostgreSQL 模式下与事实写入同事务提交。
5. 正式收据创建必须有 `Idempotency-Key` 或 body `idempotencyKey`。

## Cross-Page Dependencies

- Upstream:
  - `imports-invoices`
  - `reconciliation-workbench`
  - `pending-invoices`
  - OA projection
  - 银行流水关系
  - tax/cost lifecycle
- Downstream:
  - `tax-offset`
  - `cost-statistics`
  - `app-health-operations`
  - invoice lifecycle observers
- Required backfill order: `workbench_relation -> invoice_lifecycle -> output_invoice_collection`
- Phase 0 dependency group: `Invoice lifecycle and tax`。

## Read Model / Worker / App Status

- Read models: `output_invoice_collection`, `invoice_lifecycle`
- Worker: `invoice-usage-collection`
- Related worker: `invoice-lifecycle`
- App Status domain: `output_invoice_collections`
- Source versions include: output collection read model、invoice lifecycle policy、lifecycle facts、status rules、receipt schema、OA projection sync。
- Freshness rule: 写入 lifecycle facts 后首要刷新 `output_invoice_collection`；不能用旧 SQL 或页面私有规则伪装 fresh。

## Current Gaps To Assess Before L2

- 用户要完善的是收款状态、提醒、红蓝票关系、正式收据、详情、筛选/导出，还是 read model 状态。
- receipt create/void/reissue 的幂等和历史返回是否完整。
- 手动状态、提醒、红蓝票关系写入是否同事务 enqueue refresh。
- source version mismatch 和 `202 refreshing` 是否在前端正确处理。
- 是否存在页面私有收款状态规则或请求线程 live rebuild；L2 必须移除。

## Risks

- 权限: 查看销项收款、写手动状态/提醒/收据、导出需要权限分层。
- 审计: 手动状态、提醒、红蓝票关系、收据生命周期和导出需要审计。
- stale/fresh: workbench relation、invoice lifecycle、output collection read model 必须按顺序收敛。
- 跨页刷新: 税金抵扣、成本统计、搜索和 App Health 依赖销项事实变化。
- worker: `invoice-usage-collection` 或 `invoice-lifecycle` 失败会导致收款状态不可用。
- 导出: 收款状态、红蓝票、收据字段和筛选条件需要回归。
- 历史数据: 历史接口必须返回真实 receipt lifecycle facts，不伪造空历史。

## Test Entry Points

- Backend:
  - `tests/test_output_invoice_collection_*`
  - lifecycle service、receipt service、status rules、read model refresh 相关测试
- Frontend:
  - `web/src/test/OutputInvoiceCollectionsPage.test.tsx`
- Integration candidates:
  - 发票导入/关系更新 -> lifecycle fresh -> output collection fresh -> 页面状态更新
  - receipt create with idempotency -> history facts -> read model refresh

## Seven-Category Test Matrix

- Business core unit tests: 适用。覆盖收款状态、红蓝票关系、提醒、收据生命周期和幂等。
- Service-layer tests: 适用。覆盖 lifecycle service、receipt service、status rules、transaction-bound queue writer。
- API contract tests: 适用。覆盖列表、详情、手动状态、提醒、receipt create/void/reissue、权限/stale。
- Read model/cache/background job tests: 适用。覆盖 `output_invoice_collection`、`invoice_lifecycle`、`invoice-usage-collection`。
- Frontend component/interaction tests: 适用。覆盖筛选、详情、状态写入、提醒、收据、loading/refreshing/error。
- End-to-end business-flow integration tests: 适用。保护销项发票导入/关系到收款状态可见的关键路径。
- Existing feature regression tests: 适用。保护税金抵扣、成本统计、发票生命周期和旧收据历史。

## Docs Impact Entry

- Module docs: `docs/modules/output-invoice-collections/`
- Long-term docs likely affected when behavior changes:
  - `docs/product-specs/invoice-lifecycle.md`
  - `docs/product-specs/cost-tax.md`
  - `docs/app-architecture/runtime-and-ownership.md`
  - `docs/dev/api-contracts.md`
  - `docs/operations/runtime-worker-governance.md`
- 涉及状态规则、receipt schema、API DTO、worker 或 source versions 时必须同步长期文档。

## Legacy / Transitional Paths

- 不得请求线程同步 live rebuild。
- 页面不得私有定义销项收款状态规则。
- service 不读取 HTTP header/cookie；HTTP 映射只在 route 层完成。
- 历史 receipt 接口不得伪造空历史。

## L2 Questions

- 本轮完善目标是收款状态、提醒、红蓝票、正式收据，还是 read model 状态可见性？
- receipt 操作的幂等键、历史展示和错误恢复是否需要补强？
- source version mismatch 是否需要展示具体 source versions 或只展示 refreshing？
- 写入后等待哪些 freshness targets 才释放 UI overlay？
- 是否存在旧 live rebuild 或私有状态规则需要先删除？

## Implementation Planning Boundary

本卡片只提供 L1.5 页面基线，不包含 L2 设计或代码实施。开始本页面实现前，必须先补齐本 phase 的可实施分析和计划，明确收款状态/receipt contract、read model/worker、权限审计、旧逻辑删除、测试矩阵和文档影响。
