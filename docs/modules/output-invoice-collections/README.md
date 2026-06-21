# 销项发票收款情况 模块维护入口

- Module key: `output-invoice-collections`
- 类型: 页面模块
- Route: `/output-invoice-collections`
- Page key: `output-invoice-collections`

## 修改前必读

- `docs/product-specs/invoice-lifecycle.md`
- `docs/product-specs/cost-tax.md`
- `docs/app-architecture/pages.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/dev/api-contracts.md`
- `docs/dev/testing-closure-dependency-map.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/tax-offset/README.md`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/domain-events-lifecycle/README.md`
- `docs/modules/runtime-workers/README.md`

## 代码入口

- `web/src/pages/OutputInvoiceCollectionsPage.tsx`
- `web/src/components/outputInvoiceCollections/*`
- `web/src/features/outputInvoiceCollections/api.ts`
- `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_receipt_service.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_models.py`
- `backend/src/fin_ops_platform/services/output_invoice_collection_status_service.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_policy.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_source_versions.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/output_invoice_collection.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前边界

本模块维护销项发票收款情况页面的列表、筛选、排序、分页、详情 drawer、收款状态、提醒、红蓝票关系和正式收据生命周期。

当前事实边界：

- 列表读接口优先读取 SQL read model `output_invoice_collection`；miss/stale/schema/source version mismatch 时返回 `202` 与 `read_model_status=refreshing`，不得在请求线程同步 live rebuild。
- 生产 PostgreSQL runtime 下，SQL read repository 缺失也属于 read model unavailable：API 必须 enqueue `output_invoice_collection` 对应 month/all scope 并返回 `read_model_status=refreshing`，不能回退 `OutputInvoiceCollectionQueryService.list_rows(...)` 或返回 `live_query`。legacy/local 模式保留 query service 作为开发兼容路径。
- fresh SQL rows 在返回前叠加 lifecycle facts：`collectionStatus`、手动状态、提醒、红蓝票关系和正式收据摘要。
- 收款状态规则由 `InvoiceLifecyclePolicy` 与 `OutputInvoiceCollectionStatusRuleService` 统一判定；页面不能自定义销项收款状态规则。
- 写接口只通过 `OutputInvoiceCollectionLifecycleService` 与 `OutputInvoiceCollectionReceiptService` 写 lifecycle facts；service 不读取 HTTP header/cookie。
- 手动收款状态、提醒、红蓝票关系、收据 create/void/reissue 必须 enqueue `output_invoice_collection` scope，并在 PostgreSQL 模式下通过 transaction-bound queue writer 与事实写入同事务提交。
- 正式收据创建必须有 `Idempotency-Key` 或 body `idempotencyKey`；历史接口返回真实 receipt lifecycle facts，不伪造空历史。
- `output_invoice_collection_source_versions()` 包含销项收款 read model、invoice lifecycle policy、lifecycle facts、status rules、receipt schema 和 OA projection sync 版本。
- App Status domain `output_invoice_collections` 依赖 `output_invoice_collection`、`invoice_lifecycle` readiness，以及 `invoice-usage-collection`、`invoice-lifecycle` worker。

跨模块影响：

- 上游：发票导入、关联台关系、invoice lifecycle、pending invoice rules、OA projection、银行流水关系和 tax/cost 相关 lifecycle。
- 下游：税金抵扣、成本统计、搜索和 App Health 通过 invoice lifecycle/domain events/readiness 观察销项发票事实变化；本模块写入自身 lifecycle facts 时首要刷新 `output_invoice_collection`。
- 真实运行回填顺序必须遵守 `workbench_relation -> invoice_lifecycle -> output_invoice_collection`，不能用旧 SQL 或页面私有规则伪装 fresh。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护 Spec-first Browser e2e 业务验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/Vitest/API/integration 的覆盖映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
