# ETC发票导入模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：ETC 发票导入通过 ETC parsers/import job/reconciliation services 进入 ETC 批次和发票附件识别链路。
- 当前缺口：ETC 导入与 ETC 票据管理、发票附件、关联台候选和历史批次修复耦合较多。
- 旧代码删除条件：旧 ETC zip/parse/repair 路径不再被导入页面或工具引用。

## 职责边界

### 负责

- ETC 发票文件/ZIP 上传、过滤、解析、预览和确认。
- 触发 ETC reconciliation、附件识别和相关 lifecycle。
- 为 ETC 票据管理页面提供导入后业务事实。
- 后台导入 job 完成后，`result_summary` 必须在 affected months 已知后返回 affected month/scope 诊断信息；queued admission 阶段不得伪造下游已收敛状态。

### 不负责

- 不直接维护 ETC 票据页面 UI 状态。
- 不直接写 workbench relation/read model。
- 不处理普通发票导入模板。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| ETC 文件/ZIP | `ImportEtcInvoicesPage.tsx` | 进入 ETC import/parsing service |
| 预览确认 | import workflow | 创建 job 并持久化导入结果 |
| Reconciliation trigger | ETC services | 产生后续候选和 lifecycle |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| ETC import preview/result | 前端页面 | 可审计、可失败恢复 |
| ETC batch/invoice facts | ETC services | 供 ETC 票据管理读取 |
| Downstream impact | lifecycle/runtime queue | 影响 workbench/invoice/tax/cost 等下游 direct API 和真实后台任务；Search 只通过 direct `/api/search` 重新读取业务结果 |
| Job completion summary | background job result summary / ETC 票据页 | 后端 result summary 可返回 `affected_months`、`affected_scope_keys` 等写后影响诊断信息；不返回 `read_model_scope_keys` 等 legacy target fields。前端 background job mapper 只暴露业务可读的 affected fields，ETC 票据页消费 completed job 后直接重读业务批次/任务列表，不再等待 operation barrier 或 job target fields |

## 持久化与投影

- Own read model：无独立 manifest entry。
- Downstream impact：`workbench`、`workbench_relation`、`invoice_lifecycle`、`tax_offset`、`input_invoice_usage`、`pending_invoice`、`oa_pending_payment`、`cost_statistics` 的 direct API / lifecycle /真实后台任务；Search 不再是 refresh/read model target，只受 direct search payload 影响。
- Worker：import/runtime handlers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportEtcInvoicesPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx` |
| Frontend feature | `web/src/features/etc/api.ts`、`features/etc/types.ts`、`features/imports/importRoutes.ts` |
| Backend route | `routes_etc_import.py`、`routes_etc_invoices.py`、ETC import endpoints in `server.py` |
| Backend service | `etc_service.py`、`etc_reconciliation_service.py`、`etc_reconciliation_zip_filter.py`、`etc_document_parsers.py`、`import_processing_service.py` |
| Recognition/lifecycle | `invoice_attachment_recognition_service.py`、`derived_data_lifecycle_service.py`、`runtime_worker_handlers.py` |
| Tests | `tests/test_etc_*.py`、`tests/test_import*.py`、`web/e2e/imports-etc-invoices-flow.spec.ts` |

## 依赖方向

- 允许依赖：ETC parsers, import job queue, reconciliation service, attachment recognition。
- 必须通过：ETC import/reconciliation service。
- 禁止绕过：导入流程直接写 workbench relation；把 repair 工具作为常规 API。

## 测试与验证

- `tests/test_etc_backend.py`
- `tests/test_etc_reconciliation_import_cleanup_service.py`
- `tests/test_import_job_queue.py`
- `tests/test_import_processing_service.py`
- `web/src/test/EtcTicketManagementPage.test.tsx`
- `web/e2e/imports-etc-invoices-flow.spec.ts`

## 当前缺口和删除条件

- ETC zip parser/filter 变更必须覆盖导入、票据管理和关联台候选回归。
