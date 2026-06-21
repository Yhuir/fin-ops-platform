# ETC发票导入 模块维护入口


- Module key: `imports-etc-invoices`
- 类型: 页面模块
- Route: `/imports/etc-invoices`
- Page key: `imports.etc-invoices`

## 修改前必读

- `docs/product-specs/imports-and-etc.md`
- `docs/operations/etc-business-batches.md`
- `docs/product-specs/invoice-lifecycle.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/app-architecture/pages.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`
- `docs/modules/etc-tickets/README.md`
- `docs/modules/domain-events-lifecycle/README.md`
- `docs/modules/runtime-workers/README.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/tax-offset/README.md`
- `docs/modules/cost-statistics/README.md`

## 代码入口

- `web/src/pages/imports/ImportEtcInvoicesPage.tsx`
- `web/src/components/imports/ImportWorkflowPage.tsx`
- `web/src/features/etc/api.ts`
- `web/src/features/etc/types.ts`
- `web/src/features/imports/importRoutes.ts`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/etc_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_zip_filter.py`
- `backend/src/fin_ops_platform/services/etc_document_parsers.py`
- `backend/src/fin_ops_platform/services/import_processing_service.py`
- `backend/src/fin_ops_platform/services/invoice_attachment_recognition_service.py`
- `backend/src/fin_ops_platform/services/import_job_queue.py`
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- `backend/src/fin_ops_platform/services/app_status_job_registry.py`

## 当前边界

`/imports/etc-invoices` 只渲染 `ImportWorkflowPage mode="etc_invoice"`。页面不走通用 `/imports/files/*` 发票文件导入，而是通过 `web/src/features/etc/api.ts` 调用 `/api/etc/import/preview` 和 `/api/etc/import/confirm`。

ETC 发票导入必须绑定一个已经确认且可导入的 ETC 对账任务。预览阶段会用对账任务的 confirmed item set 过滤 zip 内发票，只允许与任务要求匹配的发票进入 import session；确认阶段会校验 task version、`confirmed_item_set_hash` 和 import session freshness，创建 `etc_invoice_import` 后台 job，并通过 `etc_invoice_import.confirm` processor 完成导入。

ETC 发票导入确认会创建或复用 task-scoped ETC business batch，写入 ETC import batch 和 ETC invoice metadata / PDF / XML 附件关系，再触发 `etc_import_confirmed` 派生生命周期。ETC ZIP 不再直接创建统一发票池事实；统一发票池 `app.invoices` 只由正式进/销项发票导入，或 OA 附件识别 service 判定为正式发票且池内不存在时受控创建。业务批次后续的 OA 草稿创建、人工确认“已提交/未提交”、删除和 summary row 释放属于 ETC 票据管理模块，但本导入模块必须把这些 fan-out 风险写入测试矩阵。

核心 fan-out：

| 动作 | 事实源 / 事件 | 影响 |
| --- | --- | --- |
| ready task 查询 | `EtcReconciliationTaskService.list_ready_for_import_tasks()` | ETC 导入页 task selector |
| zip preview | `preview_etc_zip_for_task(...)` + `EtcService.preview_import_zips(...)` | 当前导入页 preview、missing requirements、duplicate audit |
| preview stale | `stale_reconciliation_task_preview` 或 `preview_stale` | 当前导入页必须清空 preview 并要求重新预览 |
| confirm queued | `etc_invoice_import` background job、可选 `import.process.requested` | 导入页 job feedback、App Status/App Health；job source 必须携带 `task_id`、`affected_domains=["imports_etc_invoices","etc_tickets"]` 和 route `/imports/etc-invoices` |
| confirm processed | `ImportProcessingService.execute_etc_invoice_import_confirm_job(...)` | ETC business batch、ETC invoice metadata、PDF/XML 附件关系；只关联已存在 canonical invoice，不创建新 canonical invoice |
| lifecycle refresh | `etc_import_confirmed` | 关联台、ETC summary row、invoice lifecycle、税金抵扣、成本统计、历史 ETC repair、search |
| 业务批次提交/删除 | `manual-oa-status`、business batch delete | ETC 票据管理、关联台 summary row、税金/成本刷新 |

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
