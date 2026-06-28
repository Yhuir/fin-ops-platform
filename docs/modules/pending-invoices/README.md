# 待找发票 模块维护入口


- Module key: `pending-invoices`
- 类型: 页面模块
- Route: `/pending-invoices`
- Page key: `pending-invoices`

## 修改前必读

- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`

## 代码入口

- `web/src/pages/PendingInvoicesPage.tsx`
- `web/src/components/pendingInvoices/*`
- `web/src/features/pendingInvoices/api.ts`
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_sql_projection.py`

## 当前边界

关注支出/收入流水、进项/销项发票、规则建议、选择已有发票、收入状态批量标记、Search direct payload 和 invoice lifecycle 分发。发票获取状态由后端 `InvoiceLifecyclePolicy` / read boundary 给出，页面直接消费 rows/rules/filter/export API 返回的业务 DTO；这些页面 API 不返回 `read_model_status`、`read_model_stale_reasons`、`read_model_scope_key(s)` 或 `refresh_enqueued`，页面也不私有定义状态。

列表父筛选以最终 `invoice_acquisition_status.code` 为事实源；`requires_invoice` 是“需要开票”状态桶，不等同于 `filter_group='requires_invoice'`。`filter_group` / `matched_rule` 只解释规则命中，不能把生产中 `filter_group=all` 但状态为待/已开票的行排除。

页面首屏默认展示支出“需要开票”闭环中的 `paid_pending_invoice` 和 `paid_invoiced` 两类状态。已在关联台确认并进入 `paid_invoiced` 的流水仍属于待找发票闭环的核对结果，不能因为只默认筛 `paid_pending_invoice` 而从首屏消失；用户可以通过状态筛选手动收窄到仅待开票。

`pending_invoice.read_model.refresh`、`pending-invoice` RabbitMQ consumer、`SearchPendingSqlProjectionBuilder`、`PendingInvoiceReadModelRepositoryPort`、`invoice_lifecycle.read_model.refresh`、`invoice-lifecycle` / `invoice-lifecycle-secondary` worker 和 `read_model.pending_invoice_rows/scopes` 当前运行读写面已删除。前端页面按 direct rows refetch p95 <= 1000ms 验收，写操作成功后直接重读 rows，不等待 operation barrier、legacy read-model convergence 或 invoice lifecycle legacy worker。待找发票 lifecycle 行由 direct `PendingInvoiceQueryService` 组装，不再复用 pending-invoice SQL projection。

OA/流水/发票配对关系不属于待找发票页面私有状态。读关系必须通过 `WorkbenchRelationReadFacade` / `workbench_relation` distribution；attach existing 单条和批量写关系必须委托 `WorkbenchRelationCommandService`。普通 relation distribution unavailable 只影响读侧诊断 和候选展示；写 API 的阻断条件必须来自权限/session、DB/目标写模型不可用、canonical relation version/idempotency/row occupation 冲突，不能因为 distribution 追赶中先写本模块半事实。历史 manual invoice command/service 只保留为旧数据恢复和迁移兼容事实，不再通过待找发票 HTTP API 或页面 UI 暴露新写入口。

列表 rows 必须按统一 relation distribution 展示多项关系。`bank_transactions`、`input_invoices` 和 `oa` 三个分区都以 `relation_count` / `has_multiple` / `detail_mode` / `summaries` 表达 relation 成员；当某个分区成员数大于 1 时，该栏只显示代表全部成员的 `+N`，不再同时展示任一 primary 成员。多笔银行流水属于同一 relation 时，direct query service 只能输出一条聚合行，legacy read model guard 也必须保持同一约束，不能再把其它流水成员作为 standalone 行重复展示。点击 `+N` 时按 `kind=bank|invoice|oa` 打开对应类型明细，不能把其它分区混在同一次展开视图里。

选择已有进项发票只从表格上方的选中流水工具栏进入。页面可以选择一条或多条 eligible 支出流水，右侧抽屉通过批量 candidates/preview/confirm API 选择多张进项发票。候选表的“流水关联”chip 必须来自后端 `bank_relation_status` / `linked_bank_transaction_count`，不得用 `remaining_amount=0` 推断是否已关联流水；候选表不再展示“待支付”金额列。抽屉汇总展示已选流水金额、已选发票金额和“本次选择差额”，preview 后展示“关联后待付”；最终补付金额以 preview `payment_impact.remaining_amount_after` 为准。preview `can_confirm=false` 时必须展示后端 conflicts/warnings 原因，不能只禁用确认按钮。行内三点菜单和“补票”入口不是当前 UI/HTTP 契约。

收入侧支持与支出侧一致的多选，但只在 `direction=income` scope 内启用；选中后表格上方工具栏显示“标记无需开票”“标记现金收入”“清除选择”。收入批量状态写入走 `PUT /api/pending-invoices/income-statuses`，后端必须先全量校验 transaction ids、方向、重复选择、已关联销项发票和 status code，再一次性写入 command/audit/finalizer，不能逐行循环造成半成功。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或 legacy freshness 字段删除变化。
- 业务状态、UI 状态、direct payload 状态、worker 状态或状态流转变化。
- 跨页面 direct refetch、domain event、derived lifecycle、outbox/job 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `e2e-spec.md`：维护 Spec-first Browser E2E 用户流程和验收合同。
- `e2e-coverage.md`：维护 Spec ID 到 Playwright/API/integration 覆盖的映射和缺口。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
