# 银行流水导入模块边界与 I/O

日期：2026-08-06

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：银行流水导入通过 import file/service/job queue 进入预览、确认和后台处理；确认只提交 canonical facts、source version、审计与必要领域任务，不写页面 read model，也不扇出页面 refresh job。
- 当前缺口：App 内部 direct-canonical Audit 已闭环；外部银行回单页数、行数、control total 与上传前字节真实性仍须独立来源证据，不能由 App 文件登记 hash 推导。
- 旧代码删除状态：生产与前端只保留 `/imports/files/*` file/session I/O。旧 `/imports/preview`、`/imports/confirm` JSON route/handler/entrypoint、无生产者的 `general_import.confirm` worker 类型、processor、preview-only orchestration dependencies 和无 session 范围的 preview 全量 snapshot writer 已删除；`FileImportService.snapshot/from_snapshot` 只保留为跨进程恢复 I/O，不作为增量写入接口。

## 职责边界

### 负责

- 银行流水文件上传、模板识别、预览、确认导入、导入任务状态。
- 导入完成后返回精确 affected scopes；direct-canonical 下游页面下次请求在同一只读 snapshot 直接看到新 facts，只有保留的 Workbench/read-model consumer 使用自己的 freshness gateway。
- 记录导入预览审计。
- 通过统一 page Audit 在同一只读 snapshot 证明 file object、session/file、batch/row、canonical bank transaction、当前 import job/outbox 的集合、字段、引用与 queue 状态。
- Audit 比较交易时间时必须比较同一时间点：银行文件中无时区的 `trade_time` 按 `Asia/Shanghai` 解释，PostgreSQL `timestamptz` 与带时区 ISO 值统一归一到 UTC 后比较；禁止把同一时刻的本地时间与 UTC 表示误报为漂移，也禁止忽略真实的时间差异。
- 导入确认结果或完成后的 job result 必须透出 write result envelope；普通导入的 `freshness_targets` 与 `operation_barrier_targets` 固定为空，不要求当前写操作等待任意页面重建。

### 不负责

- 不直接维护银行明细页面投影。
- 不负责 no-OA、turnover 或 workbench 业务状态机。
- 不绕过 import job queue 执行长任务。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 上传文件/模板选择 | `ImportBankTransactionsPage.tsx` | 文件只进入 import API/service |
| 预览确认 | `ImportWorkflowPage.tsx`、`features/imports/api.ts` | 银行流水页面只能调用 `/imports/files/preview`、`/imports/files/confirm`、`/imports/files/sessions/*`；确认后创建可追踪 job |
| 页面手动刷新 | `ImportWorkflowPage.tsx` | 重新读取银行映射配置；有持久化 preview session 时同时精确重读该 session，保留当前草稿和文件选择，不执行浏览器 reload 或跨页面 refresh。 |
| Job event | runtime worker handlers | 后台处理必须可恢复 |

preview/confirm/retry 都属于 canonical 导入写链，必须在 multipart/JSON 解析前通过共享 mutation guard；`imported_by` 与 background job owner 只取已认证 session username，客户端 form/body 同名字段不具有身份语义。

Import worker 注册 handler 时只固定 processor 类型，不得把启动时的 `FileImportService` / canonical import snapshot 长期缓存到后续 job。每次 `import.process.requested` 执行前必须从 PostgreSQL durable facts 重新构造 processor，使 worker 启动后新创建的 session/file 以及最新 canonical 去重事实可见。

生产 API 的 session GET、confirm、retry 与 background retry 在进入 file/session service 前同样必须从 `load_imports_snapshot` + `load_file_imports_snapshot` 显式恢复当前 PostgreSQL import runtime；该恢复只属于导入操作边界，不得重新启用 `state:imports`、`state:file_imports` 或 full-state bootstrap fallback。

file/session preview/retry 只允许输出当前 `session_id`、files 与其 `preview_batch_id` 的精确 delta，且不得包含 canonical invoice/transaction facts。confirm 的持久化输出必须是本次所选 session、正式 batch 及其新建/状态更新 canonical facts 的精确 delta。合法重复行只引用既有 transaction，不重新拥有或回写该 transaction；两条链都不得回写其它 session 或未受影响 facts。调用方必须通过 `ApplicationStateStoreProtocol.save_import_delta(...)` 写入；PostgreSQL 在同一事务写 batch 与 file/session，本地实现按 batch/entity/session id 合并且计数器只增不减，二者共享“未出现在 delta 中的事实保持不变”语义。

confirm 的 I/O 顺序必须是 `save_import_delta` 原子提交在先，必要的 Workbench auto-matching 领域任务 enqueue 在后。batch 与 file/session 任一写入失败必须整体回滚且不得发布领域任务；普通 confirm 禁止发布 tax/read-model refresh，禁止让 worker 在 canonical facts 可见之前消费 scope，也禁止后台状态写入与 confirm 形成丢失更新窗口。

批次明细持久化必须复用 PostgreSQL connection 的 bounded `execute_many_values` chunk，不得按行建立数据库
round-trip；`ON CONFLICT` 的 legacy batch owner 条件和 affected-row 数必须保持 fail closed。缺少 batch capability
的 transaction 必须 fail fast，不得回退为逐行 SQL；同一事务继续承担 owner guard 与整体回滚。

通用 `Application._persist_state()` 已从 import canonical/session 写链隔离，不得再包含 `imports`、`file_imports` 或调用其全量 snapshot。preview/retry 只通过 `_persist_import_preview_delta(session_id)` 写当前 session-scoped delta，confirm 只通过上述 selected-files delta 边界持久化正式事实；OA 附件发票晋升和 ETC metadata 关联分别使用 `save_invoices` 与 `save_invoice_etc_metadata` 窄端口。

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 预览结果 | 前端导入页面 | 不持久化为业务事实直到确认 |
| 导入文件事实列表 | `/api/import-facts/files`、HTTP SLO probe | 只返回分页文件摘要字段；不得输出完整 `raw_payload`、`row_results`、`normalized_rows`，预览明细只能走 `/imports/files/*` session/preview 边界 |
| 导入 job status | background job/app status | 可查询、可失败恢复 |
| Affected scope | 页面 freshness gateway / 必要领域任务 | 返回本次写入影响的精确月份；不在写路径展开成页面 refresh jobs |
| Write result envelope | 前端导入页面/job result | 返回 `affected_scope_keys`，普通写的 `read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` 为空。前端立即结束写操作；后续访问页面由该页 freshness/status/enqueue 边界收敛 |
| Page Audit | `/api/operations/app-health/page-audit?page=imports.bank-transactions` | admin-only、只读、`read_model_keys=[]`、`relation_proof_required=false`；expected-set 同时包含本次正式 batch 拥有的 transaction 与 duplicate row 引用的历史 canonical transaction，反向 owner 唯一性只约束本批次拥有的 transaction；下游 read model 只登记为 impact targets，不冒充页面 consumer |

失败但仍可重试的 import job 必须在 admin-only Audit issue 中返回 `attempt_count/max_attempts`、`last_error`、`session_id` 和 `selected_file_ids`，使运维只能通过正式 file/session retry/confirm I/O 定位和恢复；不得要求直接查询或改写 `job.import_jobs`。

## 持久化与投影

- Own read model：无独立 manifest entry。
- 逻辑影响消费者：bank detail/account balance、`workbench`、`workbench_relation`、invoice lifecycle、pending invoice、OA pending payment、cost statistics；这些影响不等于写后立即入队，各 owner 在访问时读取已提交 facts。
- Worker：import job/runtime worker handlers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportBankTransactionsPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx` |
| Frontend feature | `web/src/features/imports/api.ts`、`types.ts`、`importRoutes.ts` |
| Backend route | import endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `import_file_service.py`、`imports.py`、`import_processing_service.py`、`import_job_queue.py`、`import_preview_audit.py` |
| Audit owner | `services/postgres_repositories/bank_transaction_import_page_audit.py`、`services/postgres_repositories/import_audit_repair.py`、`services/page_audit_registry.py` |
| Controlled repair | `services/import_audit_repair_service.py` 输出纯 plan；`tools/import_audit_repair_ops.py` 仅编排 dry-run/execute I/O |
| Worker/runtime | `runtime_worker_handlers.py`、`app_status_job_registry.py` |
| Tests | `tests/test_import*.py`、`web/src/test/ImportsApi.test.ts`、`web/e2e/imports-bank-transactions-flow.spec.ts` |

## 依赖方向

- 允许依赖：import job queue、background job service、明确的 Workbench auto-matching 领域任务端口。
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

- 模板识别变更必须覆盖预览、确认、失败恢复，以及导入后首次访问受影响页面时的 downstream freshness。
- 旧 JSON import API 及其 `general_import.confirm` worker 链已删除；测试造数只能调用保留的 service-level normalization ports，HTTP 行为必须走 file/session API。
- 删除任何 file/session snapshot 持久化前，必须先提供 import worker 跨进程恢复替代方案；不能把 `FileImportService.snapshot/from_snapshot` 误判为旧 full snapshot fallback。
- Audit pass 只证明已登记 App 内部事实闭包；外部银行 control evidence 与下游受影响页面各自的 Audit 仍是独立 gate。
- `app.import_batch_rows.legacy_mongo_id` 必须是 `batch_row:<batch_id>:<row_no>`；repository upsert 只能更新同一 `legacy_batch_id` 的行。任何跨 batch 冲突必须回滚整个事务，禁止恢复 process-global row counter 或 `ON CONFLICT` 重挂 owner 的旧逻辑。
- 历史严格合同银行批次的 row evidence 只能由已登记 import file payload 与 canonical transaction owner 共同恢复；受控工具必须先做 repeatable-read dry-run、输出 fingerprint/rollback manifest，再在 serializable advisory-lock 事务内执行。

## Canonical facts ownership

- Owned facts: `app.bank_transactions` 的导入正式化事实，以及对应 `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` 中的银行流水导入事实。
- Allowed writes: bank transaction import preview/confirm/job、import processing service、受控去重/正式化 repository。
- Allowed reads: bank transaction repository/query ports、bank detail/import API。
- Downstream outputs: bank detail/account balance、workbench、turnover ledger、no-OA batch 可比较的 canonical source-version 变化；保留 read model 的访问 gateway 创建精确 dirty scope，其他页面直接查询 canonical facts。
- Forbidden paths: 银行流水页面不得调用旧 JSON `/imports/preview`、`/imports/confirm`；production API/worker 不得从 full snapshot、local pickle、`state:imports`、`state:full_state` 或前端 payload 直接补写银行流水。
- Old code deletion: 已删除旧 JSON HTTP route/handler/entrypoint、`general_import.confirm` job producer/processor 及只为该链服务的 preview scope dependencies；snapshot 银行流水 fallback、直接跨模块写银行事实路径必须保持删除。migration/audit/rollback 工具和 file/session worker restore 端口保留不算 closure。

## Audit v19 provenance 版本边界（2026-07-12）

- migration 0101 为新 `app.import_files` 设置 `audit_contract_revision=import-page-audit.v1` 默认值，但不回填历史行。
- 当前 revision 的新导入必须严格证明 file object/hash/session/batch/row/canonical transaction 全链路与双向 expected-set；任何缺失均阻断 Audit。
- revision 为 NULL 的 pre-contract 历史只输出 `legacy_provenance_unproven` warning；不得补造文件对象、hash 或 session。历史 canonical 银行流水仍由银行明细及下游页面 Audit 证明。
