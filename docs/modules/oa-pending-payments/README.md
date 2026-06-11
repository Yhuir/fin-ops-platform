# OA待付款核对 模块维护入口


- Module key: `oa-pending-payments`
- 类型: 页面模块
- Route: `/oa-pending-payments`
- Page key: `oa-pending-payments`

## 修改前必读

- `docs/architecture/oa-integration.md`
- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `web/src/pages/OaPendingPaymentsPage.tsx`
- `web/src/components/oaPendingPayments/*`
- `web/src/features/oaPendingPayments/api.ts`
- `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_service.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_details.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_source_versions.py`

## 当前边界

关注 OA 单据、支出银行流水、进项发票、Workbench relation、SQL read model、invoice lifecycle 分发、详情 drawer 和异常反馈。OA 待付款以 OA 申请为主行，`paymentStatus` 由 `InvoiceLifecyclePolicy` 或等价 lifecycle read boundary 判定；页面不得自行定义付款状态。

生产读路径必须先经过 `OaPendingPaymentReadModelService` 的 freshness/source-version gate。rows、filter-options、OA detail、bank detail、invoice detail 和 relation detail 在 read model missing/stale/source mismatch 时只能返回 refreshing/unavailable 语义并入队 `oa_pending_payment.read_model.refresh`，不能同步 live scan 旧事实并伪装 fresh。

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
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
