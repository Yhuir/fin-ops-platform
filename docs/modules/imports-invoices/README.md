# 发票导入 模块维护入口


- Module key: `imports-invoices`
- 类型: 页面模块
- Route: `/imports/invoices`
- Page key: `imports.invoices`

## 修改前必读

- `docs/product-specs/imports-and-etc.md`
- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/modules/domain-events-lifecycle/README.md`
- `docs/modules/runtime-workers/README.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/tax-offset/README.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/cost-statistics/README.md`

## 代码入口

- `web/src/pages/imports/ImportInvoicesPage.tsx`
- `web/src/components/imports/ImportWorkflowPage.tsx`
- `web/src/features/imports/api.ts`
- `web/src/features/imports/types.ts`
- `web/src/app/importRoutes.ts`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/import_file_service.py`
- `backend/src/fin_ops_platform/services/imports.py`
- `backend/src/fin_ops_platform/services/import_processing_service.py`
- `backend/src/fin_ops_platform/services/import_job_queue.py`
- `backend/src/fin_ops_platform/services/import_preview_audit.py`
- `backend/src/fin_ops_platform/services/invoice_header_fact_repair_service.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_job_registry.py`

## 当前边界

`/imports/invoices` 只渲染 `ImportWorkflowPage mode="invoice"`。共享导入工作流负责文件选择、每文件票据方向选择、预览、重复审计、确认、后台 job 反馈和 session restore。

当前发票导入支持每个文件指定 `input_invoice` 或 `output_invoice` batch type。前端预览调用 `/imports/files/preview`，以 multipart `file_overrides` 传 `template_code=invoice_export` 和 `batch_type`；确认调用 `/imports/files/confirm`，返回后台 job 或已确认 session。旧 `/imports/preview`、`/imports/confirm` JSON 写入入口已删除，HTTP 只有 file/session API。

税务平台多 sheet 工作簿若包含唯一的 `发票基础信息`，该 sheet 是每张 canonical 发票的唯一表头事实源；不得因前面的 `信息汇总表` 可以解析就提前返回。`信息汇总表` 只作为同票商品/服务行证据附着到表头行，不参与 canonical 金额、税额、价税合计或商品行字段的顶层赋值。`发票基础信息` 重名、无法识别、无有效发票或与明细强身份不一致时整文件 fail closed，不回退旧首 sheet 链；不含该 sheet 的历史单 sheet 模板继续使用共享模板识别合同。

导入确认不是所有下游页面已经完成读取的证明。确认只能说明发票事实写入或确认 job 已排队；job 完成后，关联台、待找发票、税金抵扣、进项发票使用、销项收款、OA 待付款和成本统计分别通过下一次 canonical normal GET 读取已提交事实。共享 `workbench_relation` 与 matching 仍按自己的 durable worker 合同收敛，不得恢复 Workbench page refresh 或已退休 Search runtime。

核心 fan-out：

| 动作 | 事实源 / 事件 | 影响 |
| --- | --- | --- |
| 文件预览 | `FileImportSession`、`ImportPreviewAuditCounts` | 当前导入页重复审计和 confirm eligibility |
| 文件确认排队 | `file_import` background job + durable `import.process.requested` | 导入页 job feedback、App Status import worker；发票文件确认必须进入 PostgreSQL durable queue，并报告 `affected_domains=["imports_invoices"]` 和 route `/imports/invoices`；RabbitMQ 仅可选 wakeup |
| 文件确认处理 | `ImportNormalizationService.confirm_import(...)` | input/output invoice facts、source links、duplicate decisions |
| 发票导入生命周期 | `invoice_import_confirmed` | canonical invoice/source-link versions、Workbench relation/matching；各 direct 页面下次 normal GET 读取，已退休 page/Search projection不入队 |
| 预览过期 | API `409 preview_stale` | 当前导入页必须要求重新预览，不能继续确认旧结果 |

页面统一 Audit 不读取下游 read model。它独立证明已登记 input/output file/session、batch/row、canonical invoice 与 `manual_invoice_import` source-link 的双向集合和关键字段，并仅以归属于这些 session/file 的 job/outbox 判断 queue。下游页面必须继续通过各自 Audit 证明，原始税务导出是否漏票也必须由外部对账证明。

## 维护触发器

发生以下变化时，更新本目录对应维护文档，并按影响范围同步长期事实源：

- 页面入口、路由、侧栏、筛选、排序、分页、导出、drawer/dialog 或权限显示变化。
- API contract、DTO shape、错误字段、权限校验、状态值或响应 freshness 字段变化。
- 业务状态、UI 状态、read model 状态、worker 状态或状态流转变化。
- 跨页面刷新、domain event、derived lifecycle、dirty scope、outbox 或缓存边界变化。
- 测试入口、回归范围、验证命令或未测风险变化。

## 本目录文件

- `e2e-spec.md`：维护 Spec-first Browser E2E 合同。
- `e2e-coverage.md`：维护 Spec ID 到自动化覆盖和未测风险的映射。
- `state-machine.md`：维护当前有效状态和状态流转；不适用时写明原因。
- `tests.md`：维护七类测试适用性、现有测试入口、验证命令和回归范围。
- `implementation-notes.md`：维护提炼后的决策和验收记录；不保存原始 prompt。
