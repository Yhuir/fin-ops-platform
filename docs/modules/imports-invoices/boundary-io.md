# 发票导入模块边界与 I/O

日期：2026-06-26

## 模块化状态

- 状态：partial
- 当前边界可信度：medium
- 目标边界：发票导入通过 import service/job queue 进入预览、确认和 lifecycle，触发 invoice lifecycle/search/input/output read model 刷新。
- 当前缺口：导入路径同时影响进项、销项、待找发票和搜索，变更必须明确下游 scopes。
- 旧代码删除条件：旧同步导入或直接状态写入不再被 API/测试引用。

## 职责边界

### 负责

- 发票文件上传、模板识别、预览、确认导入和导入 job。
- 将导入结果转化为发票源事实和 lifecycle event。
- 通过 derived lifecycle 触发相关 read model。
- 导入确认结果或完成后的 job result 必须透出 read model write target envelope，覆盖 tax/invoice/search/pending/input/output/cost/workbench 下游 targets。

### 不负责

- 不直接处理页面 read model projection。
- 不直接维护进项使用、销项收款或待找发票业务规则。
- 不绕过 import preview audit。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 上传文件/模板选择 | `ImportInvoicesPage.tsx` | 文件先进入 import file service |
| 预览确认 | `ImportWorkflowPage.tsx` | 确认后创建 job/正式化 |
| Job event | import job queue | 后台可恢复处理 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 预览 rows/errors | 前端页面 | 未确认前不作为业务事实 |
| 导入结果 | state store/repository | 可审计、可幂等 |
| Dirty scope | derived lifecycle/runtime queue | invoice lifecycle/search/input/output/pending invoice |
| Write target envelope | 前端导入页面/job result | 返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`；background job mapper 会标准化 result summary targets，消费 completed job 的页面必须先等待 targets |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 影响 read model：`tax_offset`、`invoice_lifecycle`、`pending_invoice`、`input_invoice_usage`、`output_invoice_collection`、`search`、`workbench`、`workbench_relation`、`oa_pending_payment`、`cost_statistics`。
- Worker：import job/runtime handlers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportInvoicesPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx` |
| Frontend feature | `web/src/features/imports/api.ts`、`types.ts`、`importRoutes.ts` |
| Backend route | import endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `import_file_service.py`、`imports.py`、`import_processing_service.py`、`import_job_queue.py`、`import_preview_audit.py` |
| Lifecycle/worker | `derived_data_lifecycle_service.py`、`runtime_worker_handlers.py` |
| Tests | `tests/test_import*.py`、`tests/test_invoice_*.py`、`web/e2e/imports-invoices-flow.spec.ts` |

## 依赖方向

- 允许依赖：import service, lifecycle service, invoice identity/lifecycle services。
- 必须通过：preview -> confirm -> job/lifecycle。
- 禁止绕过：确认前直接改业务事实；导入 service 直接写 read model projection。

## 测试与验证

- `tests/test_import_formalization_api.py`
- `tests/test_import_preview_audit.py`
- `tests/test_import_service.py`
- `tests/test_import_processing_service.py`
- `web/src/test/BackgroundJobProgress.test.tsx`
- `web/src/test/ImportsApi.test.ts`
- `web/e2e/imports-invoices-flow.spec.ts`

## 当前缺口和删除条件

- 发票模板变更必须覆盖进项/销项/待找/search 的 downstream fresh 状态。
- 删除旧同步导入路径前，必须证明确认响应/job result 仍能给出所有下游 read model 的 operation barrier targets。
