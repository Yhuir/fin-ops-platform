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
- `backend/src/fin_ops_platform/services/oa_pending_payment_command_service.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_details.py`
- `backend/src/fin_ops_platform/services/oa_payment_admitted_projection.py`
- `backend/src/fin_ops_platform/services/oa_payment_status_service.py`
- `backend/src/fin_ops_platform/services/mongo_oa_adapter.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_source_versions.py`

## 当前边界

关注 OA 单据、支出银行流水、进项发票、Workbench relation、SQL read model、invoice lifecycle 分发、OA MySQL 支付状态写回、详情 drawer 和异常反馈。OA 待付款以 OA 申请为主行，`paymentStatus` 由 `InvoiceLifecyclePolicy` / `OaPendingPaymentQueryService` 或等价 lifecycle read boundary 判定；页面不得自行定义付款状态。

页面支持 `view_mode=completed|in_progress`：

- OA 待付款核对的准入事实源是 OA MySQL `t_payment_simple.flow_id`，不是 OA Mongo 全量。页面/read model 先读取该表的有效 `flow_id`，再用 `flow_id` 匹配 OA Mongo `form_data._id`；只有匹配成功的 OA 才进入正常表格。
- `t_payment_simple.id` 只是支付状态记录 ID，可作为诊断/内部记录 ID，不是 OA ID；OA 匹配和写回必须使用 `flow_id`。
- `completed` 是原 OA 待付款视图，只展示已进入 `t_payment_simple` 且当前已完成或历史未带 workflow status 的 OA，并继续展示 OA、支付状态、支出流水和进项发票 relation 证据。
- `in_progress` 只展示已进入 `t_payment_simple` 且 OA 系统当前仍为进行中的支付申请/日常报销。表格 UI 与 `completed` 使用同一套 OA、支付状态、流水、发票四分组结构；候选流水只作为证据展示，必须由用户点击“确认已支付”后才允许确认 relation 并写回 OA MySQL。
- `summary.viewCounts.completed/in_progress` 按同一批 `t_payment_simple.flow_id` 准入后的 OA 当前 workflow status 计算，用于页面切换按钮数量；筛选和搜索条件会同步作用于该数量。
- 普通 `app.oa_applications` 投影只服务已完成/历史未知 OA；本页面不再依赖普通 projection 扫进行中 OA，而是通过 `PaymentAdmittedOAProjectionAdapter` 以 `t_payment_simple.flow_id` 为准入表，精确读取 OA Mongo 当前记录后再按 `view_mode` 过滤。OA 系统里未进入 `t_payment_simple` 的重复/异常流程不展示。
- 进行中 OA 视图中的 OA 写回状态来自 `t_payment_simple.flow_id`。2026-06-17 实机验证显示该字段对应 OA Mongo `form_data._id`，平台用 Mongo OA detail fields 中的 `Mongo文档ID` 或 `oa-pay-/oa-exp-` 行 ID 后缀解析；流程实例 ID 和流程请求 ID 只保留为详情/诊断字段。
- 应用正常运行时通过 MySQL 连接配置写回 OA 支付状态，不要求应用进程登录服务器 SSH；SSH 只属于人工运维/排障通道。

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
