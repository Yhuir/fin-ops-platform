# 发票导入模块边界与 I/O

日期：2026-08-23

## 模块化状态

- 状态：implemented-and-auditable
- 当前边界可信度：high（App 内部合同；外部税务来源证据仍独立）
- 目标边界：发票导入通过 import service/job queue 进入预览和确认；确认只提交 canonical facts、source version、审计与必要领域任务，不在写后触发页面 read model fan-out。
- 当前缺口：外部税务平台导出完整性、原始文件 control total 和对象字节可读性仍需独立证据。
- 旧代码删除状态：旧 JSON preview/confirm、file confirm inline 写入、batch revert、`app.import_files.import_batch_id` 反推链、无 session 范围的 preview 全量 snapshot writer，以及待找发票 service 中直接创建发票并绑定流水的旧手工录入链均已删除并由 guard 保护。

## 职责边界

### 负责

- 发票文件上传、模板识别、预览、确认导入和导入 job。
- 多张发票人工录入；每张可点击或拖拽 JPG/JPEG/PNG/PDF，识别只负责预填，用户逐张“保存信息”后整批执行服务端校验并生成一个普通 `FileImportSession`。导入页复用既有 confirm job；关联台的 OA 补录入口使用受限的跨模块原子提交边界，使整批发票与指定 OA 子付款项关系同成同败。
- XLSX 统一通过有界共享 reader 读取；对来源文件错误声明的 worksheet dimension 先重算可见范围，再执行模板识别、行数/单元格/压缩比资源门禁，不为发票建立第二条 parser 链。
- 多 sheet 税务导出若存在唯一 `发票基础信息`，只从该 sheet 生成 canonical invoice facts；`信息汇总表` 仅提供同票明细证据。表头 sheet 重名、无有效行、模板不合法或明细强身份不能唯一归属时 fail closed，禁止回退到首个可解析 sheet。历史单 sheet 文件仍走共享模板识别。
- 将导入结果转化为发票源事实与精确 affected scopes。
- 所有下游页面在下次请求的同一只读 snapshot 中直接看到已提交 facts；Workbench 自动匹配仅使用独立领域 dirty-scope worker，不是页面读取依赖。
- 导入确认结果或完成后的 job result 必须透出 canonical write result envelope；不得返回已退役的 page target、freshness 或 operation-barrier 字段。
- 每次进入页面都使用空白本地草稿，不从浏览器存储或活跃 session 列表恢复历史预览；用户显式放弃时，只终结当前认证用户拥有的未确认 preview，不改发票 canonical facts。

### 不负责

- 不直接处理页面 read model projection。
- 不直接维护进项使用、销项收款或待找发票业务规则。
- 不绕过 import preview audit。
- 不拥有补充凭证元数据、文件对象、上传或软删除；统一查看只调用关联台 owner 的只读 gallery/content API。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 上传文件/模板选择 | `ImportInvoicesPage.tsx` | 文件先进入 import file service |
| 可选单张附件识别 | `POST /imports/invoices/manual/recognize` | 每次只接收当前发票的一份 JPG/JPEG/PNG/PDF；图片走统一图片规范化和 OCR，PDF 先读原生文本，无可识别发票时逐页 OCR 并在首张发票命中后停止。只返回允许预填的发票字段，不写业务事实，也不保留上传文件。 |
| 多张人工预览 | `POST /imports/invoices/manual/preview` | 请求体固定为 `invoices[]`。每张票据方向、红蓝字、购销双方、票号/条件式代码、日期和金额税率由服务端校验；红字表单收正数、canonical 金额统一转负数。同批重复或任一现存/疑似重复整批返回 `409` 并终结预览，不允许部分进入发票池；成功后生成当前用户的一个 `FileImportSession` 和与发票一一对应的 `file_ids[]`。 |
| 预览确认 | `ImportWorkflowPage.tsx` | 确认后创建 job/正式化 |
| 预览陈旧校验 | `FileImportService.assert_session_preview_current` | 除汇总 audit counts 外逐行比较 decision、linked object type/id；数量不变但 canonical invoice owner 调换仍返回 `preview_stale`，不得确认旧预览。错误只报告字段名和变化数量。 |
| 当前预览读取/放弃 | `GET /imports/files/sessions/{session_id}`、`POST /imports/files/discard` | 页面只读取本次访问创建并持有 id 的 session；不提供活跃 session 列表或自动恢复。放弃校验 owner 并事务化终结 file/session/pending batch；已确认或已创建活跃/成功 job 时拒绝。 |
| 复核明细分页 | `GET /imports/files/sessions/{session_id}/review-rows?kind=duplicate|unimported&offset&limit` | `limit` 最大 100；返回当前 session 的稳定切片和 `total/has_more`。发票行输出发票号码、开票日期、销方、购方、金额、税额、价税合计等用户复核字段；不得套用银行账户/交易方向字段。 |
| 页面手动刷新 | `ImportWorkflowPage.tsx` | 有持久化 preview session 时精确重读 `/imports/files/sessions/{session_id}`；保留当前草稿和文件选择，不执行浏览器 reload 或跨页面 refresh。 |
| 补充凭证统一查看 | `GET /api/workbench/oa-invoice-supplements/gallery` | 仅在发票导入页抽屉打开后按 9 条 cursor page 读取 active 元数据；图片/PDF 缩略图 lazy load，点击后读取既有 content API。零 mutation、零 import session、零 relation/matching/read-model/worker I/O。 |
| Job event | import job queue | 后台可恢复处理；相同 import idempotency key 只接受相同 request fingerprint。瞬时失败归还 pending 并由 durable outbox 重试，达到最大次数才终态失败；用户再次确认同一请求时，terminal failed/partial job 必须原子复用原 job id 并重新 queued/pending，禁止新建冲突 job；活跃 processing lease 不得被并发 worker 接管。 |
| Background job progress | background job repository | 只按 canonical `job_id` 单行更新；禁止全量回写历史 background job snapshot，历史 raw payload 的旧 id 不得污染发票导入事务。 |

preview/confirm/retry 都属于 canonical 导入写链，必须在 multipart/JSON 解析前通过共享 mutation guard；`imported_by` 与 background job owner 只取已认证 session username，客户端 form/body 同名字段不具有身份语义。

preview 首次登记 `app.import_files` 时必须同时写入认证 username 到 `uploaded_by` 与 `raw_payload.normalized_payload.imported_by`，最终 session delta 必须保持同值；当前 session 读取和放弃只使用该服务端 owner 事实。session/file/batch/canonical candidate ID 使用带业务前缀的 UUID，不使用进程内顺序号或“先查询再递增”的多 worker 竞态分配。

file/session preview/retry 只允许通过当前 `session_id` 持久化该 session、files 与其 `preview_batch_id` 的精确 delta，且不得携带 canonical `invoices` / `transactions`；不得把进程内其它历史 session/batch 的 snapshot 写回 PostgreSQL。preview 的 `suspected_duplicate` 可保留候选 invoice 引用作为复核证据，confirm 后 terminal row 必须清空该非权威引用；`created`、`status_updated`、`duplicate_skipped` 的正式引用保持不变。发票 confirm 必须在同一事务内锁定本批强身份命中的 canonical 发票、持久化所选 session / batch / invoice delta，并只对本批身份集合式读取当前 OA attachment cache；命中强身份和明确 OA 子付款项时合并 OA 来源边，保留既有 OA / 明细归属 / 导入 provenance，再在同一事务标记必要的 Workbench matching scope。`disabled` promotion mode 不合并 OA 来源；其它模式在本批 canonical 已存在后只允许 link-existing，不得借此创建 cache 中其它发票。持久化或来源合并失败时 batch、file/session、canonical invoice、来源边和 matching dirty 必须整体回滚，领域任务不得半发布。普通 confirm 不发布 tax/read-model refresh。

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| 预览 rows/errors | 前端页面 / `app.import_batches` / `app.import_batch_rows` / `app.import_files` | 未确认前不作为业务事实；只写当前 session/preview batches，不得携带正式 `invoices` / `transactions` facts，也不得覆盖其它 session 的 terminal 状态。session GET 只返回摘要，重复/未导入明细经有界分页 API 读取。 |
| 导入页人工录入确认 | `/imports/files/confirm` | 只使用 manual preview 返回的 session 和全部 `file_ids[]`；与 Excel 导入共用 durable `file_import.confirm`、canonical invoice identity、source link、审计和失败回滚。不得自动建立 OA/银行流水关系。 |
| 关联台人工补录确认 | `POST /api/workbench/oa-invoice-supplements/manual` | 仅接受当前认证用户拥有的完整 `manual_invoice_entry` session；在一个 PostgreSQL 事务中确认全部发票、写 canonical import facts、增加精确 `oa_expense_item_invoice` 来源边，并通过正式 relation command 创建或扩展目标关系。任一步失败同时恢复 import runtime 与 relation runtime，不留下半批发票或半关系。该窄入口不改变导入页的 durable job 合同。 |
| 导入文件事实列表 | `/api/import-facts/files`、HTTP SLO probe | 只返回分页文件摘要字段；不得输出完整 `raw_payload`、`row_results`、`normalized_rows`，预览明细只能走 `/imports/files/*` session/preview 边界 |
| 导入结果 | state store/repository | 可审计、可幂等；确认异常必须回滚 import service 与 file session 内存状态。相同 fingerprint 的失败确认通过正式 confirm I/O 复用原 job id；不同 fingerprint 返回结构化 `409 idempotency_conflict`。 |
| Affected scope | 前端 / 必要领域任务 | 返回本次 canonical 写入影响的精确月份，不在写路径展开为页面 refresh jobs |
| Write result envelope | 前端导入页面/job result | 只返回当前 canonical 写合同字段与 `affected_scope_keys`；前端立即结束写操作，页面访问负责直接重读 |

## 持久化与投影

- Own read model：无；App 内不存在 read model manifest。
- Page Audit：`imports.invoices` 是 direct-canonical 页面；在同一 repeatable-read read-only snapshot 内证明 file/session/batch/row、canonical invoice、`manual_invoice_import` source-link 与本页 job/outbox。
- 下游 direct-canonical consumer：税金抵扣与成本统计在 import job 提交 `app.invoices` 后由各自页面 GET 直接读取新事实，不等待页面 read model。
- 其他消费者：Workbench、发票生命周期、待找发票、进/销项、OA 待付款、税金和成本均通过各自 canonical query API 读取；`workbench-matching` 只负责候选匹配领域任务。
- Worker：import job/runtime handlers。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/imports/ImportInvoicesPage.tsx` |
| Frontend components | `web/src/components/imports/ImportWorkflowPage.tsx`、`ManualInvoiceEntryDrawer.tsx`、`ManualInvoiceBatchEditor.tsx`、`SupportingDocumentGalleryDrawer.tsx` |
| Cross-module read client | `web/src/features/workbench/api.ts`、`types.ts`；补充凭证 owner 仍在 reconciliation-workbench |
| Frontend feature | `web/src/features/imports/api.ts`、`types.ts`、`importRoutes.ts` |
| Backend route | import endpoints in `backend/src/fin_ops_platform/app/server.py` |
| Backend service | `manual_invoice_entry_service.py`、`oa_attachment_invoice_service.py`、`import_file_service.py`、`imports.py`、`workbench_invoice_supplement_service.py`、`import_processing_service.py`、`import_job_queue.py`、`import_preview_audit.py`、`import_lifecycle_service.py` |
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
- `tests/test_workbench_invoice_supplement_service.py`
- `tests/test_workbench_invoice_supplement_api.py`
- `tests/test_import_lifecycle_service.py`
- `web/src/test/ImportCenterPage.test.tsx`
- `web/src/test/SupportingDocumentGalleryDrawer.test.tsx`
- `web/src/test/WorkbenchApi.test.ts`
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
