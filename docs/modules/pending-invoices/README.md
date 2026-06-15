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
- `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_sql_projection.py`

## 当前边界

关注支出/收入流水、进项/销项发票、规则建议、选择已有发票、收入状态批量标记、搜索/read model 状态和 invoice lifecycle 分发。发票获取状态由 `InvoiceLifecyclePolicy` / `invoice_lifecycle` read boundary 与 pending invoice read model 共同表达，页面不私有定义状态。

生产刷新由专用 `pending-invoice` 与 `search` RabbitMQ consumers 承担 5s SLO drain；旧 `search-pending` combined worker 保留为兼容消费者，不再是唯一性能 lane。`invoice_lifecycle` 另有 `invoice-lifecycle-secondary` 并发消费者用于多月份 scope 收敛。

OA/流水/发票配对关系不属于待找发票页面私有状态。读关系必须通过 `WorkbenchRelationReadFacade` / `workbench_relation` distribution；attach existing 单条和批量写关系必须委托 `WorkbenchRelationCommandService`。普通 relation read model 非 fresh 只影响读侧 freshness 和候选展示；写 API 的阻断条件必须来自权限/session、DB/目标写模型不可用、canonical relation version/idempotency/row occupation 冲突，不能因为 distribution 追赶中先写本模块半事实。历史 manual invoice command/service 只保留为旧数据恢复和迁移兼容事实，不再通过待找发票 HTTP API 或页面 UI 暴露新写入口。

选择已有进项发票只从表格上方的选中流水工具栏进入。页面可以选择一条或多条 eligible 支出流水，右侧抽屉通过批量 candidates/preview/confirm API 选择多张进项发票，并展示已选流水金额、已选发票金额和差额。行内三点菜单和“补票”入口不是当前 UI/HTTP 契约。

收入侧支持与支出侧一致的多选，但只在 `direction=income` scope 内启用；选中后表格上方工具栏显示“标记无需开票”“标记现金收入”“清除选择”。收入批量状态写入走 `PUT /api/pending-invoices/income-statuses`，后端必须先全量校验 transaction ids、方向、重复选择、已关联销项发票和 status code，再一次性写入 command/audit/finalizer，不能逐行循环造成半成功。

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
