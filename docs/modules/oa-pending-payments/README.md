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

- `completed` 视图读取普通 `app.oa_applications` / OA completed projection；这是统一事实源中的已完成/历史未知 OA，不受 OA MySQL `t_payment_simple` 准入表限制。
- `in_progress` 视图的准入事实源才是 OA MySQL `t_payment_simple.flow_id`。页面/read model 先读取该表的有效 `flow_id`，再用 `flow_id` 匹配 OA Mongo `form_data._id`；只有匹配成功且当前仍进行中的 OA 才进入进行中表格。
- `t_payment_simple.id` 只是支付状态记录 ID，可作为诊断/内部记录 ID，不是 OA ID；OA 匹配和写回必须使用 `flow_id`。
- `in_progress` 不得用 completed projection 的金额、对方、项目、事由等业务字段做反向排除；业务允许同项目、同供应商、同金额、同事由发起多张不同 OA。不同 `flow_id` 是不同付款申请，是否展示只由 `t_payment_simple.flow_id` 准入和当前 workflow status 决定。
- `completed` 是原 OA 待付款视图，只展示统一 OA projection 中当前已完成或历史未带 workflow status 的 OA，并继续展示 OA、支付状态、支出流水和进项发票 relation 证据。
- `in_progress` 只展示已进入 `t_payment_simple` 且 OA 系统当前仍为进行中的支付申请/日常报销。表格 UI 与 `completed` 使用同一套 OA、支付状态、流水、发票四分组结构；页面进入后会调用自动匹配/写回命令，复用关联台 OA-bank 精确金额/精确合计规则，将未配对支出流水自动确认为 Workbench active relation，并在金额、方向和 `flow_id` 校验通过后写回 OA MySQL。
- `in_progress` 仍保留“关联支出流水”右侧抽屉，作为自动匹配失败后的人工兜底。抽屉默认展示全部支出流水，并可按全部、未配对、已配对、已关联进行中 OA 筛选；只有未配对流水可选择并建立 Workbench active relation。该关联成功后同样触发自动写回：支出流水合计等于 OA 金额且可解析 `flow_id` 时，把 `t_payment_simple.pay_status` 写成已支付，并让表格 chip 从“未写回”刷新为“已写回”。
- `completed` 和 `in_progress` 只要已经存在有效支出流水 active relation 且支出合计等于 OA 金额，都由自动写回命令写回 `t_payment_simple.pay_status=1`；页面不再提供人工“确认已支付并写回”按钮。
- `summary.viewCounts.completed/in_progress` 分别按 completed 统一 OA projection 与 in-progress payment-admitted projection 计算；筛选和搜索条件会同步作用于该数量。
- 普通 `app.oa_applications` 投影只服务已完成/历史未知 OA；本页面的 completed 视图读取该统一 projection，in-progress 视图通过 `PaymentAdmittedOAProjectionAdapter` 以 `t_payment_simple.flow_id` 为准入表，精确读取 OA Mongo 当前记录后再按 `view_mode` 过滤。OA 系统里未进入 `t_payment_simple` 的重复/异常进行中流程不展示。
- 进行中 OA 视图中的 OA 写回状态来自 `t_payment_simple.flow_id`。2026-06-17 实机验证显示该字段对应 OA Mongo `form_data._id`，平台用 Mongo OA detail fields 中的 `Mongo文档ID` 或 `oa-pay-/oa-exp-` 行 ID 后缀解析；流程实例 ID 和流程请求 ID 只保留为详情/诊断字段。
- 应用正常运行时通过 MySQL 连接配置写回 OA 支付状态，不要求应用进程登录服务器 SSH；SSH 只属于人工运维/排障通道。

生产读路径必须先经过 `OaPendingPaymentReadModelService` 的 freshness/source-version gate。rows、filter-options、OA detail、bank detail、invoice detail 和 relation detail 在 read model missing/stale/source mismatch 时只能返回 refreshing/unavailable 语义并入队 `oa_pending_payment.read_model.refresh`，不能同步 live scan 旧事实并伪装 fresh。

`oa_pending_payment:all` 在 refresh 链路中是 fan-out 到月份 shard 的控制 scope；页面默认 all 查询的 freshness 证明来自实际 rows/month scopes 和 active dirty/outbox 状态。month scope 必须继续严格比对对应月份 `workbench_relation` source versions；all 查询不能直接使用全局 `workbench_relation:all` source versions 作为 expected contract，否则会把已 fresh 的月份 shard 误判为 stale 并反复显示“正在刷新”。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `e2e-spec.md`：维护 Spec-first Browser E2E 用户流程和验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/API/integration 覆盖的映射和缺口。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
