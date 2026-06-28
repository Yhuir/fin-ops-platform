
> 2026-06-28：invoice usage collection read model runtime 已下线；本文中旧 refresh/worker/port 名称仅作为历史迁移记录，不是当前运行合同。

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
- `backend/src/fin_ops_platform/services/invoice_usage_collection_source_versions.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/output_invoice_collection.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`

## 当前边界

本模块维护销项发票收款情况页面的列表、筛选、排序、分页、详情 drawer、收款状态、提醒、红蓝票关系和正式收据生命周期。

当前事实边界：

- 页面首屏、筛选、导出预览和导出直接消费业务 API 返回的 rows、filter-options、export-preview 和 xlsx 文件。页面 API 不返回 `readModelStatus`、`read_model_status`、`readModelScopeKey`、`read_model_scope_key` 或 refresh flags；页面不自动轮询 freshness，不因 legacy 诊断字段隐藏表格或禁用导出。
- 后端 `output_invoice_collection` SQL projection/read model 和 worker 合同只作为 legacy 删除记录；页面级 fresh gate service 已删除，后续清理残余 projection/worker 文档时同步移除对应 runtime/tests/docs。
- direct rows 由 query service 在返回前叠加 lifecycle facts：`collectionStatus`、手动状态、提醒、红蓝票关系和正式收据摘要。
- 页面展示统一关系事实源中的 OA、收入流水和销项发票项：rows 中 `oa`、`bankTransactions`、`invoiceRelations` 都携带 `relationCount`、`hasMultiple`、`detailMode` 和 `summaries`；同一 relation 下多项对象在对应栏显示 `+N`，其中 `N=relationCount-1` 表示除主展示对象外的额外项数，点击 `/rows/{row_id}/relation-details?kind=oa|bank|invoice` 展开全部明细。销项发票栏多项时仍显示当前行的发票主信息和多张发票合计，避免只剩 `+N` 无合计。
- 收款状态规则由 `InvoiceLifecyclePolicy` 与 `OutputInvoiceCollectionStatusRuleService` 统一判定；页面不能自定义销项收款状态规则。
- 写接口只通过 `OutputInvoiceCollectionLifecycleService` 与 `OutputInvoiceCollectionReceiptService` 写 lifecycle facts；service 不读取 HTTP header/cookie。
- 手动收款状态、提醒、红蓝票关系、收据 create/void/reissue 只写 lifecycle facts / receipt facts；不再 enqueue `output_invoice_collection` page read-model scope。页面写成功后 direct refetch rows/detail/history。
- 手动收款状态、提醒、红蓝票关系、收据 create/void/reissue 响应仅保留 `affected_scope_keys` 作为写后影响 scope 诊断，不再返回 legacy target fields。前端写成功后直接 refetch rows，不再请求 operation barrier。
- 正式收据创建必须有 `Idempotency-Key` 或 body `idempotencyKey`；历史接口返回真实 receipt lifecycle facts，不伪造空历史。
- `output_invoice_collection_source_versions()` 仍用于过渡期 legacy projection/worker；页面 rows/filter/detail/export 不再读取 SQL payload freshness。
- `output_invoice_collection:all` 在 legacy refresh 链路中是 fan-out 到月份 shard 的控制 scope；该规则只约束后端过渡 projection/worker，不作为页面 direct API 的 freshness 证明。month scope 在 legacy projection 内仍必须继续严格比对对应月份 `workbench_relation` source versions；all 查询不能直接使用全局 `workbench_relation:all` source versions 作为 expected contract，否则会让旧 projection 反复入队。
- `Application` 不再保留 output collection app-level projection helpers；`list_output_invoice_collection_scope_shards(...)`、`mark_output_invoice_collection_scope_empty(...)` 和 `rebuild_output_invoice_collection_read_model_scope(...)` 仅作为 legacy cleanup/compatibility 边界名出现，不是当前页面读取路径。
- App Status domain `output_invoice_collections` 不再依赖 `invoice_lifecycle` readiness 或 `invoice-lifecycle` worker；页面写后 direct refetch rows/detail/export API。`output_invoice_collection` legacy projection 仍只作为过渡兼容对象，不是页面 freshness proof。

跨模块影响：

- 上游：发票导入、关联台关系、pending invoice rules、OA projection、银行流水关系和 tax/cost 相关 lifecycle。
- 下游：税金抵扣、成本统计、搜索和 App Health 通过 direct API/domain events 观察销项发票事实变化；本模块写入自身 lifecycle facts 后首要重读业务 GET。
- 真实运行不再要求等待 `invoice_lifecycle` legacy worker；页面不得用旧 SQL 或私有规则伪装 direct API payload。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应字段变化。
- 业务状态、UI 状态、legacy projection/worker 下线状态或状态流转变化。
- 跨页面 direct refetch、domain event、derived lifecycle、affected scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `e2e-spec.md`：维护 Spec-first Browser e2e 业务验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/Vitest/API/integration 的覆盖映射。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
