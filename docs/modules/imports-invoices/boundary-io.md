# 发票导入模块边界与 I/O

日期：2026-07-22

## 模块化状态

- 状态：implemented-and-auditable
- 当前边界可信度：high（App 内部合同；外部税务来源证据仍独立）
- 目标边界：发票导入通过 import service/job queue 进入预览、确认和 lifecycle，触发 invoice lifecycle/search/input/output read model 刷新。
- 当前缺口：外部税务平台导出完整性、原始文件 control total 和对象字节可读性仍需独立证据。
- 旧代码删除状态：旧 JSON preview/confirm、file confirm inline 写入、batch revert、`app.import_files.import_batch_id` 反推链和无 session 范围的 preview 全量 snapshot writer 均已删除并由 guard 保护。

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

file/session preview/retry 只允许通过当前 `session_id` 持久化该 session、files 与其 `preview_batch_id` 的精确 delta，且不得携带 canonical `invoices` / `transactions`；不得把进程内其它历史 session/batch 的 snapshot 写回 PostgreSQL。confirm 必须先通过 `save_import_delta` 在同一事务持久化所选 session、batch 与 canonical invoice 精确 delta，成功后才允许发布 tax/read-model invalidation 和 Workbench matching。持久化失败时 batch 与 file/session 必须整体回滚，且下游发布数必须为零。

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 预览 rows/errors | 前端页面 / `app.import_batches` / `app.import_batch_rows` / `app.import_files` | 未确认前不作为业务事实；只写当前 session/preview batches，不得携带正式 `invoices` / `transactions` facts，也不得覆盖其它 session 的 terminal 状态 |
| 导入文件事实列表 | `/api/import-facts/files`、HTTP SLO probe | 只返回分页文件摘要字段；不得输出完整 `raw_payload`、`row_results`、`normalized_rows`，预览明细只能走 `/imports/files/*` session/preview 边界 |
| 导入结果 | state store/repository | 可审计、可幂等；确认异常必须回滚 import service 与 file session 内存状态 |
| Dirty scope | derived lifecycle/runtime queue | invoice lifecycle/search/input/output/pending invoice |
| Write target envelope | 前端导入页面/job result | 返回 `affected_scope_keys`、`read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets`；background job mapper 会标准化 result summary targets。前端只在 targets 非空时等待 operation barrier；targets 为空时直接完成反馈，禁止读取 Workbench 页面猜测刷新状态 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- Page Audit：`imports.invoices` 是 `read_model_keys=()`、`relation_proof_required=false` 的 direct-canonical 页面；在同一 repeatable-read read-only snapshot 内证明 file/session/batch/row、canonical invoice、`manual_invoice_import` source-link 与本页 job/outbox。
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
| Controlled repair | `services/import_audit_repair_service.py`（纯 plan）、`services/postgres_repositories/import_audit_repair.py`（SQL I/O）、`tools/import_audit_repair_ops.py`（CLI 编排） |
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

## Canonical facts ownership

- Owned facts: `app.invoices` 的导入正式化事实，以及对应 `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` 中的发票导入事实。
- Allowed writes: invoice import preview/confirm/job、`ImportNormalizationService`、受控 OA/ETC 现有发票 link/promotion adapter。
- Allowed reads: invoice import facts repository、发票查询/context ports、owner API。
- Downstream outputs: invoice lifecycle、pending invoice、input/output invoice usage、search、workbench、workbench_relation、tax、cost read model dirty scopes 或 owner producer 输出。
- Forbidden paths: production API/worker 不得从 full snapshot、local pickle、`state:imports`、`state:full_state` 或 OA/ETC cache 直接构造第二发票池。
- Old code deletion: 旧同步导入、直接状态写入、snapshot 发票池 fallback、batch revert 和从 `app.import_files.import_batch_id` 反推 file session 状态的 fallback 已删除；历史 migration/只读 audit 工具不构成 runtime fallback。
- Durable confirm：`/imports/files/confirm` 必须创建 `job.import_jobs(import_type=file_import.confirm)` 与 `job.outbox_events(event_type=import.process.requested)`；PostgreSQL polling 与 RabbitMQ wakeup 共用该 gateway，queue/repository 不可用返回 `503 import_queue_unavailable`，禁止进程内确认。
- 2026-07-22：文件预览保存改为 `FileImportService.preview_session_persistence_payload(session_id)`，只写当前 session 和 `preview_batch_id`；删除 `ImportNormalizationService.snapshot(include_facts=False)` 与无参全量 preview writer。PostgreSQL `save_import_delta` 在同一事务写 batch 与 file/session，防止 stale API 覆盖其它已确认导入或形成半写状态。

## Audit v19 provenance 版本边界（2026-07-12）

- migration 0101 为新 `app.import_files` 设置 `audit_contract_revision=import-page-audit.v1` 默认值，但不回填历史行。
- 当前 revision 的新导入严格证明 file object/hash/session/batch/row/canonical invoice 与 source link；税率按语义归一化比较，例如 `1% == 0.01`。
- revision 为 NULL 的 pre-contract 历史保留明确 warning，不伪造来源证据；canonical 发票、展示字段和 relation 完整性由对应业务页面 Audit 阻断证明。
- 税局导出的一张发票可以包含多条商品/服务/折扣明细。preview 在同一文件内按数电票号或代码+号码聚合互不重复的明细金额、税额和价税合计；完全相同的重复行仍保留给 duplicate audit；“部分重复 + 部分不同”或表头身份冲突必须 fail closed。
- 当前严格合同 Audit 对历史多行发票按同一 batch + canonical invoice 重算合计后比较；不得把第一条物理明细误当整票金额，也不得把完全相同的重复行二次加总。
- 历史金额恢复只能更新 source batch 仍一致的 canonical invoice，并由 repeatable-read dry-run fingerprint、serializable transaction 和 rollback manifest 约束；运行时导入链不调用该修复工具。
