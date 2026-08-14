# 发票导入模块边界与 I/O

日期：2026-08-14

## 模块化状态

- 状态：implemented-and-auditable
- 当前边界可信度：high（App 内部合同；外部税务来源证据仍独立）
- 目标边界：发票导入通过 import service/job queue 进入预览和确认；确认只提交 canonical facts、source version、审计与必要领域任务，不在写后触发页面 read model fan-out。
- 当前缺口：外部税务平台导出完整性、原始文件 control total 和对象字节可读性仍需独立证据。
- 旧代码删除状态：旧 JSON preview/confirm、file confirm inline 写入、batch revert、`app.import_files.import_batch_id` 反推链、无 session 范围的 preview 全量 snapshot writer，以及待找发票 service 中直接创建发票并绑定流水的旧手工录入链均已删除并由 guard 保护。

## 职责边界

### 负责

- 发票文件上传、模板识别、预览、确认导入和导入 job。
- 单张发票人工录入；可选 JPG/JPEG/PDF 识别只负责预填，用户输入经服务端校验后生成普通 file import preview，并复用既有 confirm job。
- XLSX 统一通过有界共享 reader 读取；对来源文件错误声明的 worksheet dimension 先重算可见范围，再执行模板识别、行数/单元格/压缩比资源门禁，不为发票建立第二条 parser 链。
- 多 sheet 税务导出若存在唯一 `发票基础信息`，只从该 sheet 生成 canonical invoice facts；`信息汇总表` 仅提供同票明细证据。表头 sheet 重名、无有效行、模板不合法或明细强身份不能唯一归属时 fail closed，禁止回退到首个可解析 sheet。历史单 sheet 文件仍走共享模板识别。
- 将导入结果转化为发票源事实与精确 affected scopes。
- Direct-canonical 下游页面在下次请求的同一只读 snapshot 中直接看到已提交 facts；只有保留的 `workbench_relation` read-model consumer 使用自己的 freshness gateway，关联台页面不使用。
- 导入确认结果或完成后的 job result 必须透出 write result envelope；普通导入的 read model targets 与 operation barrier targets 为空。
- 以服务端 session/file/batch/job 事实恢复当前用户待确认预览；用户显式放弃时，只终结未确认 preview，不改发票 canonical facts。

### 不负责

- 不直接处理页面 read model projection。
- 不直接维护进项使用、销项收款或待找发票业务规则。
- 不绕过 import preview audit。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 上传文件/模板选择 | `ImportInvoicesPage.tsx` | 文件先进入 import file service |
| 可选单张附件识别 | `POST /imports/invoices/manual/recognize` | 只接收第一份 JPG/JPEG/PDF；PDF 先读原生文本，无可识别发票时逐页 OCR 并在首张发票命中后停止。只返回允许预填的发票字段，不写业务事实。 |
| 单张人工预览 | `POST /imports/invoices/manual/preview` | 票据方向、红蓝字、购销双方、票号/条件式代码、日期和金额税率由服务端校验；红字表单收正数、canonical 金额统一转负数；精确重复返回 `409`。成功后只生成当前用户的普通 `FileImportSession`。 |
| 预览确认 | `ImportWorkflowPage.tsx` | 确认后创建 job/正式化 |
| 预览陈旧校验 | `FileImportService.assert_session_preview_current` | 除汇总 audit counts 外逐行比较 decision、linked object type/id；数量不变但 canonical invoice owner 调换仍返回 `preview_stale`，不得确认旧预览。错误只报告字段名和变化数量。 |
| 预览恢复/放弃 | `GET /imports/files/sessions?mode=invoice`、`POST /imports/files/discard` | 服务端仅列出当前认证用户的活跃预览。放弃校验 owner 并事务化终结 file/session/pending batch；已确认或已创建活跃/成功 job 时拒绝。 |
| 复核明细分页 | `GET /imports/files/sessions/{session_id}/review-rows?kind=duplicate|unimported&offset&limit` | `limit` 最大 100；返回当前 session 的稳定切片和 `total/has_more`。发票行输出发票号码、开票日期、销方、购方、金额、税额、价税合计等用户复核字段；不得套用银行账户/交易方向字段。 |
| 页面手动刷新 | `ImportWorkflowPage.tsx` | 有持久化 preview session 时精确重读 `/imports/files/sessions/{session_id}`；保留当前草稿和文件选择，不执行浏览器 reload 或跨页面 refresh。 |
| Job event | import job queue | 后台可恢复处理；相同 import idempotency key 只接受相同 request fingerprint。瞬时失败归还 pending 并由 durable outbox 重试，达到最大次数才终态失败；用户再次确认同一请求时，terminal failed/partial job 必须原子复用原 job id 并重新 queued/pending，禁止新建冲突 job；活跃 processing lease 不得被并发 worker 接管。 |
| Background job progress | background job repository | 只按 canonical `job_id` 单行更新；禁止全量回写历史 background job snapshot，历史 raw payload 的旧 id 不得污染发票导入事务。 |

preview/confirm/retry 都属于 canonical 导入写链，必须在 multipart/JSON 解析前通过共享 mutation guard；`imported_by` 与 background job owner 只取已认证 session username，客户端 form/body 同名字段不具有身份语义。

preview 首次登记 `app.import_files` 时必须同时写入认证 username 到 `uploaded_by` 与 `raw_payload.normalized_payload.imported_by`，最终 session delta 必须保持同值；恢复、列出和放弃只使用该服务端 owner 事实。session/file/batch/canonical candidate ID 使用带业务前缀的 UUID，不使用进程内顺序号或“先查询再递增”的多 worker 竞态分配。

file/session preview/retry 只允许通过当前 `session_id` 持久化该 session、files 与其 `preview_batch_id` 的精确 delta，且不得携带 canonical `invoices` / `transactions`；不得把进程内其它历史 session/batch 的 snapshot 写回 PostgreSQL。confirm 必须先通过 `save_import_delta` 在同一事务持久化所选 session、batch 与 canonical invoice 精确 delta，成功后才允许发布必要的 Workbench auto-matching 领域任务；普通 confirm 不发布 tax/read-model refresh。持久化失败时 batch 与 file/session 必须整体回滚，且领域任务发布数必须为零。

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 预览 rows/errors | 前端页面 / `app.import_batches` / `app.import_batch_rows` / `app.import_files` | 未确认前不作为业务事实；只写当前 session/preview batches，不得携带正式 `invoices` / `transactions` facts，也不得覆盖其它 session 的 terminal 状态。session GET 只返回摘要，重复/未导入明细经有界分页 API 读取。 |
| 人工录入确认 | `/imports/files/confirm` | 只使用 manual preview 返回的 session/file id；与 Excel 导入共用 durable `file_import.confirm`、canonical invoice identity、source link、审计和失败回滚。不得自动建立 OA/银行流水关系。 |
| 导入文件事实列表 | `/api/import-facts/files`、HTTP SLO probe | 只返回分页文件摘要字段；不得输出完整 `raw_payload`、`row_results`、`normalized_rows`，预览明细只能走 `/imports/files/*` session/preview 边界 |
| 导入结果 | state store/repository | 可审计、可幂等；确认异常必须回滚 import service 与 file session 内存状态。相同 fingerprint 的失败确认通过正式 confirm I/O 复用原 job id；不同 fingerprint 返回结构化 `409 idempotency_conflict`。 |
| Affected scope | 页面 freshness gateway / 必要领域任务 | 返回本次 canonical 写入影响的精确月份，不在写路径展开为页面 refresh jobs |
| Write result envelope | 前端导入页面/job result | 返回 `affected_scope_keys`；普通写的 `read_model_scope_keys`、`freshness_targets`、`operation_barrier_targets` 为空。前端立即结束写操作，页面访问负责精确收敛 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- Page Audit：`imports.invoices` 是 `read_model_keys=()`、`relation_proof_required=false` 的 direct-canonical 页面；在同一 repeatable-read read-only snapshot 内证明 file/session/batch/row、canonical invoice、`manual_invoice_import` source-link 与本页 job/outbox。
- 下游 direct-canonical consumer：税金抵扣与成本统计在 import job 提交 `app.invoices` 后由各自页面 GET 直接读取新事实，不等待页面 read model。
- 保留 read-model 消费者：`workbench`、`workbench_relation`；其余发票生命周期、待找发票、进/销项、OA 待付款、税金和成本均为 direct-canonical 消费者。Search runtime 没有当前入口。
- Worker：import job/runtime handlers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportInvoicesPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx`、`ManualInvoiceEntryDrawer.tsx` |
| Frontend feature | `web/src/features/imports/api.ts`、`types.ts`、`importRoutes.ts` |
| Backend route | import endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `manual_invoice_entry_service.py`、`oa_attachment_invoice_service.py`、`import_file_service.py`、`imports.py`、`import_processing_service.py`、`import_job_queue.py`、`import_preview_audit.py`、`import_lifecycle_service.py` |
| Lifecycle persistence | `services/postgres_repositories/import_lifecycle.py`；聚合既有 import facts/job，不新增表、队列或 read model。 |
| Controlled repair | `services/import_audit_repair_service.py`、`services/invoice_header_fact_repair_service.py`（纯 plan）、`services/postgres_repositories/import_audit_repair.py`（SQL I/O）、`tools/import_audit_repair_ops.py`（CLI 编排）；发票表头事实修复只接受批准的工作簿 SHA-256 和 11 张精确 allowlist，dry-run/execute 指纹绑定并保留 rollback manifest；生命周期修复只接受显式 batch/file，且必须由 succeeded job + 行计数 + canonical/source-link 闭环证明；放弃预览的 payload 修复只接受显式 reverted batch，并证明严格 file/session 已终结且无 job/canonical ownership |
| Worker/runtime | `runtime_worker_handlers.py` |
| Tests | `tests/test_import*.py`、`tests/test_invoice_*.py`、`web/e2e/imports-invoices-flow.spec.ts` |

## 依赖方向

- 允许依赖：import service、invoice identity service、明确的 Workbench auto-matching 领域任务端口。
- 必须通过：preview -> confirm -> durable job -> canonical commit。
- 禁止绕过：确认前直接改业务事实；导入 service 直接写 read model projection。

## 测试与验证

- `tests/test_import_formalization_api.py`
- `tests/test_import_preview_audit.py`
- `tests/test_import_service.py`
- `tests/test_import_processing_service.py`
- `web/src/test/BackgroundJobProgress.test.tsx`
- `web/src/test/ImportsApi.test.ts`
- `tests/test_manual_invoice_entry_service.py`
- `web/src/test/ManualInvoiceEntryDrawer.test.tsx`
- `tests/test_import_lifecycle_service.py`
- `web/src/test/ImportCenterPage.test.tsx`
- `web/e2e/imports-invoices-flow.spec.ts`

## 当前缺口和删除条件

- 发票模板变更必须覆盖导入后首次访问进项/销项/待找时的 downstream 展示状态。
- 普通导入不得恢复下游 operation barrier targets；显式运维 refresh 才能返回并等待其明确 targets。
- 普通发票 XLS/XLSX 与银行文件共享签名、容器资源上限和 SHA-256 文件级防重；同内容改名后不得再次确认。

## Canonical facts ownership

- Owned facts: `app.invoices` 的导入正式化事实，以及对应 `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` 中的发票导入事实。
- Allowed writes: invoice import preview/confirm/job、`ImportNormalizationService`、受控 OA/ETC 现有发票 link/promotion adapter。
- Allowed reads: invoice import facts repository、发票查询/context ports、owner API。
- Downstream outputs: invoice lifecycle、pending invoice、input/output invoice usage、OA pending、tax、cost 直接读取 canonical facts；`workbench`、`workbench_relation` 按自身访问/maintenance 合同使用精确 dirty scope。
- Forbidden paths: production API/worker 不得从 full snapshot、local pickle、`state:imports`、`state:full_state` 或 OA/ETC cache 直接构造第二发票池。
- Old code deletion: 旧同步导入、直接状态写入、snapshot 发票池 fallback、已确认 batch 撤销链和从 `app.import_files.import_batch_id` 反推 file session 状态的 fallback 已删除；仅保留 owner 校验后对未确认 preview 的显式放弃，该路径不触及 canonical invoice。
- Durable confirm：`/imports/files/confirm` 必须创建 `job.import_jobs(import_type=file_import.confirm)` 与 `job.outbox_events(event_type=import.process.requested)`；PostgreSQL polling 与 RabbitMQ wakeup 共用该 gateway，queue/repository 不可用返回 `503 import_queue_unavailable`，禁止进程内确认。
- 2026-07-22：文件预览保存改为 `FileImportService.preview_session_persistence_payload(session_id)`，只写当前 session 和 `preview_batch_id`；删除 `ImportNormalizationService.snapshot(include_facts=False)` 与无参全量 preview writer。PostgreSQL `save_import_delta` 在同一事务写 batch 与 file/session，防止 stale API 覆盖其它已确认导入或形成半写状态。
- 2026-07-22：历史上已被 stale preview 降级的单条生命周期事实通过现有 `import-audit-repair` 边界修复；必须显式提供 `--batch-id` 与 `--file-id`，dry-run 指纹和 execute 必须一致，且只允许 `pending/preview_ready -> completed/confirmed` 的精确转换。旧 preview 同时清空的 import row link 只能按 `(batch_id, source_unique_key/data_fingerprint)` 唯一匹配既存 `manual_invoice_import` source-link 后恢复；其它中间态、活跃 job、计数不符、多义匹配或 canonical/source-link 不闭环一律 fail closed。
- 2026-08-11：放弃 preview 必须在同一事务同步 `app.import_batches.status` 与 batch formal payload status 为 `reverted`；Audit 将该状态视为合法终态。历史上已产生的精确 mismatch 只通过 `import-audit-repair --normalize-reverted-batch-id` 修复 payload 单字段，要求严格 file/session 均已 reverted、无 active/succeeded job、无 linked import row、无 canonical invoice/source-link；dry-run fingerprint 变化或任一前置条件不符时零写入。

## Audit v19 provenance 版本边界（2026-07-12）

- migration 0101 为新 `app.import_files` 设置 `audit_contract_revision=import-page-audit.v1` 默认值，但不回填历史行。
- 当前 revision 的新导入严格证明 file object/hash/session/batch/row/canonical invoice 与 source link；税率按语义归一化比较，例如 `1% == 0.01`。
- revision 为 NULL 的 pre-contract 历史保留明确 warning，不伪造来源证据；canonical 发票、展示字段和 relation 完整性由对应业务页面 Audit 阻断证明。
- 当前 revision 发票可能同时保留已登记 strict batch 与已存在 pre-contract invoice batch 的 `manual_invoice_import` source-link。严格双向 equality 只比较当前 revision batch/row 对应的边；已存在 legacy invoice batch 的边继续由 provenance warning 标记为未证明，不伪报 strict orphan。引用不存在的 batch 或非发票 batch 仍必须阻断。
- canonical invoice 可以同时拥有正式 `manual_invoice_import` 与附加 `etc_invoice_import` provenance。Audit 校验 `source_batch_id` 时接受它精确命中的 manual batch 或 ETC source-link batch；没有任何精确 source-link 支撑的 owner 仍阻断。新的 ETC metadata merge 不得再覆盖既有正式 import owner。
- 税务平台标准多 sheet 导出的一张发票可以包含多条商品/服务/折扣明细。唯一 `发票基础信息` 行直接提供整票金额、税额和价税合计；`信息汇总表` 的不同明细仅保存在 `invoice_line_items` 来源证据中，不重算或覆盖表头事实。仅对不含 `发票基础信息` 的历史单 sheet 模板保留原有同票明细聚合合同。
- 当前严格合同 Audit 必须按导入时记录的 sheet role 选择事实口径：header-driven 导入比较 `发票基础信息`，历史 detail-only 导入才按同一 batch + canonical invoice 重算合计；两者都不得把第一条物理商品明细误当整票金额。
- 本次 11 张历史表头事实恢复只更新批准号码的 canonical 发票金额、税额、价税合计、空表头税率和 provenance；保留 invoice ID、关系、source link 与明细证据，并由工作簿 hash、精确计数、repeatable-read dry-run fingerprint、serializable transaction、CAS 和 rollback manifest 约束。运行时导入链不调用修复工具。
- `0134` 是一次性 provenance 修复：仅当 canonical 发票已有 `oa_attachment_invoice`、正式 import row 仍精确指向该发票、对应 `manual_invoice_import(batch_id, source_id)` 却缺失时，从 durable batch/row 事实恢复全部来源边和原 owner。无 OA 交集、无行证据、多义或已完整的发票零写；运行时不保留扫描或 fallback。
