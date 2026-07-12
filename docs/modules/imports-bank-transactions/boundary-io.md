# 银行流水导入模块边界与 I/O

日期：2026-07-11

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：银行流水导入通过 import file/service/job queue 进入预览、确认、后台处理和 derived lifecycle，不直接写页面 read model。
- 当前缺口：App 内部 direct-canonical Audit 已闭环；外部银行回单页数、行数、control total 与上传前字节真实性仍须独立来源证据，不能由 App 文件登记 hash 推导。
- 旧代码删除状态：生产与前端只保留 `/imports/files/*` file/session I/O。旧 `/imports/preview`、`/imports/confirm` JSON route/handler/entrypoint、无生产者的 `general_import.confirm` worker 类型、processor 和 preview-only orchestration dependencies 已删除；`FileImportService.snapshot/from_snapshot` 保留为当前 file/session 与 import worker 跨进程恢复 I/O，不属于旧 snapshot 事实源 fallback。

## 职责边界

### 负责

- 银行流水文件上传、模板识别、预览、确认导入、导入任务状态。
- 通过后台任务和 lifecycle 触发银行明细及下游 read model 刷新。
- 记录导入预览审计。
- 通过统一 page Audit 在同一只读 snapshot 证明 file object、session/file、batch/row、canonical bank transaction、当前 import job/outbox 的集合、字段、引用与 queue 状态。
- 导入确认结果或完成后的 job result 必须透出 read model write target envelope；银行流水导入必须包含 `bank_detail:<month>` 与 `bank_account_balance:all` operation barrier targets。

### 不负责

- 不直接维护银行明细页面投影。
- 不负责 no-OA、turnover 或 workbench 业务状态机。
- 不绕过 import job queue 执行长任务。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 上传文件/模板选择 | `ImportBankTransactionsPage.tsx` | 文件只进入 import API/service |
| 预览确认 | `ImportWorkflowPage.tsx`、`features/imports/api.ts` | 银行流水页面只能调用 `/imports/files/preview`、`/imports/files/confirm`、`/imports/files/sessions/*`；确认后创建可追踪 job |
| Job event | runtime worker handlers | 后台处理必须可恢复 |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 预览结果 | 前端导入页面 | 不持久化为业务事实直到确认 |
| 导入文件事实列表 | `/api/import-facts/files`、HTTP SLO probe | 只返回分页文件摘要字段；不得输出完整 `raw_payload`、`row_results`、`normalized_rows`，预览明细只能走 `/imports/files/*` session/preview 边界 |
| 导入 job status | background job/app status | 可查询、可失败恢复 |
| Dirty scope | derived lifecycle/runtime queue | bank_detail/workbench/search 等受影响 scope |
| Write target envelope | 前端导入页面/job result | 返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`；background job mapper 会标准化 result summary targets，消费 completed job 的页面必须先等待 targets |
| Page Audit | `/api/operations/app-health/page-audit?page=imports.bank-transactions` | admin-only、只读、`read_model_keys=[]`、`relation_proof_required=false`；下游 read model 只登记为 impact targets，不冒充页面 consumer |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 影响 read model：`bank_detail`、`bank_account_balance`、`workbench`、`workbench_relation`、`invoice_lifecycle`、`search`、`pending_invoice`、`oa_pending_payment`、`cost_statistics`。
- Worker：import job/runtime worker handlers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportBankTransactionsPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx` |
| Frontend feature | `web/src/features/imports/api.ts`、`types.ts`、`importRoutes.ts` |
| Backend route | import endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `import_file_service.py`、`imports.py`、`import_processing_service.py`、`import_job_queue.py`、`import_preview_audit.py` |
| Audit owner | `services/postgres_repositories/bank_transaction_import_page_audit.py`、`services/page_audit_registry.py` |
| Worker/lifecycle | `runtime_worker_handlers.py`、`derived_data_lifecycle_service.py`、`app_status_job_registry.py` |
| Tests | `tests/test_import*.py`、`web/src/test/ImportsApi.test.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts` |

## 依赖方向

- 允许依赖：import job queue, background job service, derived lifecycle。
- 必须通过：`ImportWorkflowPage` file/session API、`FileImportService`、`ImportProcessingService`、import job queue。
- 禁止绕过：银行流水页面回到 `/imports/preview` / `/imports/confirm` JSON 入口；导入确认时直接写 read model；长任务直接跑在 HTTP request 中；`server.py` 重新持有 import confirm processor 业务逻辑。

## 测试与验证

- `tests/test_import_api.py`
- `tests/test_import_job_queue.py`
- `tests/test_import_processing_service.py`
- `tests/test_audit_bank_transaction_import_page.py`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_server_no_longer_owns_import_confirm_processors`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_server_no_longer_exposes_legacy_json_import_write_routes`
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_bank_transaction_import_frontend_uses_file_session_api_only`
- `web/src/test/BackgroundJobProgress.test.tsx`
- `web/src/test/ImportsApi.test.ts`
- `web/e2e/imports-bank-transactions-flow.spec.ts`

## 当前缺口和删除条件

- 模板识别变更必须覆盖预览、确认、失败恢复和 downstream freshness。
- 旧 JSON import API 及其 `general_import.confirm` worker 链已删除；测试造数只能调用保留的 service-level normalization ports，HTTP 行为必须走 file/session API。
- 删除任何 file/session snapshot 持久化前，必须先提供 import worker 跨进程恢复替代方案；不能把 `FileImportService.snapshot/from_snapshot` 误判为旧 full snapshot fallback。
- Audit pass 只证明已登记 App 内部事实闭包；外部银行 control evidence 与下游受影响页面各自的 Audit 仍是独立 gate。

## Canonical facts ownership

- Owned facts: `app.bank_transactions` 的导入正式化事实，以及对应 `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` 中的银行流水导入事实。
- Allowed writes: bank transaction import preview/confirm/job、import processing service、受控去重/正式化 repository。
- Allowed reads: bank transaction repository/query ports、bank detail/import API。
- Downstream outputs: bank_detail、bank_account_balance、workbench、turnover_ledger、no_oa_bank_batch、search read model dirty scopes 或 owner producer 输出。
- Forbidden paths: 银行流水页面不得调用旧 JSON `/imports/preview`、`/imports/confirm`；production API/worker 不得从 full snapshot、local pickle、`state:imports`、`state:full_state` 或前端 payload 直接补写银行流水。
- Old code deletion: 已删除旧 JSON HTTP route/handler/entrypoint、`general_import.confirm` job producer/processor 及只为该链服务的 preview scope dependencies；snapshot 银行流水 fallback、直接跨模块写银行事实路径必须保持删除。migration/audit/rollback 工具和 file/session worker restore 端口保留不算 closure。
