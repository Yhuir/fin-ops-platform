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
- `backend/src/fin_ops_platform/services/pending_invoice_canonical_query.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py`

## 当前边界

页面只调用 `/api/pending-invoices/*`。生产只读请求由 `PendingInvoiceCanonicalQueryService` 和 `PostgresPendingInvoiceCanonicalRepository` 直接读取 PostgreSQL canonical facts；route 只负责鉴权、参数转交与 HTTP 映射。页面不读取 `pending_invoice`、`bank_detail`、`workbench_relation` 或 `search` read model，不再展示或轮询 `read_model_status`、`source_versions`、refresh job，也没有 202/fallback 分支。

rows、summary、全期间 statistics、filter options、筛选、排序、服务端分页和导出使用 bounded set-based SQL。一次 rows 响应在同一个显式 `REPEATABLE READ / READ ONLY` snapshot 内读取 app settings 与页面查询；固定两次 SELECT，不逐行/逐组访问数据库，不先把全量 payload 加载到 Python 或浏览器。

页面事实来自 `app.bank_transactions`、`app.bank_transaction_categories`、`app.bank_transaction_category_confirmations`、`app.pending_invoice_manual_invoice_commands`、`app.invoices`、`app.oa_applications`、`app.app_settings`。正式配对关系只来自 `app.workbench_pair_relations` 中 `status='active'` 的事实，并排除 `relation_mode='turnover_manual_closure'`；跨月 relation 不按当前月截断。

状态仍由已有 `pending_invoice_status_payload` 业务策略校验：支出/收入/现金收入、`paid_invoiced`、无需开票、OA/进销项覆盖、规则优先级和收入 override 口径不变。SQL 分类结果若与领域策略不一致会失败，而不是静默返回另一套口径。

候选发票、流水/发票/OA 详情和 relation detail 同样走页面 canonical repository。选择已有发票、收入状态、规则保存的权限、审计、幂等、CAS/占用冲突和 command/relation 写模型保持不变；写成功后页面重新 GET canonical facts，不等待 read-model barrier。

`pending_invoice`、`search-pending`、`invoice_lifecycle` 页面 projection/worker 与独立 Search runtime 已删除。`workbench_relation` 共享 distribution 仅供仍登记消费者使用，本页面直接读取 canonical facts，不消费它。

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
