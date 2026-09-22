# 发票导入模块边界与 I/O

日期：2026-08-23

## 2026-09-20 ETC 来源隔离

- 正式发票读取以结构化 `tax_rate` 为准，包括合法空值；不再从 ETC 污染的 normalized payload 补值。ETC 原始税率仍保存在 ETC 自有事实中。
- ETC 关联只经 canonical invoice metadata port 写入其自有字段；人工/OA 来源、正式导入 owner 与财务字段保持原值。正式发票先到、ETC 先到两个顺序遵循同一边界。
- 旧 ETC 财务补值分支、逐行 metadata writer 与 payload 税率优先读取已删除。历史副本修复使用 `import_audit_repair_ops --repair-etc-invoice-payload`：先读取正式列、原导入行与 ETC 来源证据，只在原正式税率为空且副本值来自 ETC 时清除副本值；不修改正式税额/金额或 ETC 事实，不增加普通 API。

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
| 多张人工预览 | `POST /imports/invoices/manual/preview` | 请求体固定为 `invoices[]`。每张票据方向、红蓝字、购销双方、票号/条件式代码、日期和金额税率由服务端校验；红字表单收正数、canonical 金额统一转负数。同批重复、非 OA 来源的现存发票或疑似重复整批返回 `409` 并终结预览；已由 OA 来源持有的相同强身份允许 `duplicate_skipped`，只记导入历史，不允许部分进入发票池；成功后生成当前用户的一个 `FileImportSession` 和与发票一一对应的 `file_ids[]`。 |
| 预览确认 | `ImportWorkflowPage.tsx` | 确认后创建 job/正式化 |
| 预览陈旧校验 | `FileImportService.assert_session_preview_current` | 除汇总 audit counts 外逐行比较 decision、linked object type/id；数量不变但 canonical invoice owner 调换仍返回 `preview_stale`，不得确认旧预览。错误只报告字段名和变化数量。 |
| 当前预览读取/放弃 | `GET /imports/files/sessions/{session_id}`、`POST /imports/files/discard` | 页面只读取本次访问创建并持有 id 的 session；不提供活跃 session 列表或自动恢复。放弃校验 owner 并事务化终结 file/session/pending batch；已确认或已创建活跃/成功 job 时拒绝。 |
| 复核明细分页 | `GET /imports/files/sessions/{session_id}/review-rows?kind=duplicate|unimported&offset&limit` | `limit` 最大 100；返回当前 session 的稳定切片和 `total/has_more`。发票行输出发票号码、开票日期、销方、购方、金额、税额、价税合计等用户复核字段；不得套用银行账户/交易方向字段。 |
| 页面手动刷新 | `ImportWorkflowPage.tsx` | 有持久化 preview session 时精确重读 `/imports/files/sessions/{session_id}`；保留当前草稿和文件选择，不执行浏览器 reload 或跨页面 refresh。 |
| 补充凭证统一查看 | `GET /api/workbench/oa-invoice-supplements/gallery` | 仅在发票导入页抽屉打开后按 9 条 cursor page 读取 active 元数据；图片/PDF 缩略图 lazy load，点击后读取既有 content API。零 mutation、零 import session、零 relation/matching/read-model/worker I/O。 |
| Import job | `job.import_jobs` | 唯一 prepare/commit 状态源；worker 直接 claim、租约续期与 fencing。相同意图失败重试复用原 job；确认范围变化仅在前一任务成功且显式版本匹配后创建下一意图。业务事实、审计、必要 dirty scopes 与成功状态同事务提交。 |
| 全局导入进度 | `ImportWorkflowService` | 只读投影 canonical import job；不维护第二套 background job。 |

preview/confirm/retry 都属于 canonical 导入写链，必须在 multipart/JSON 解析前通过共享 mutation guard；`imported_by` 与 background job owner 只取已认证 session username，客户端 form/body 同名字段不具有身份语义。

preview 首次登记 `app.import_files` 时必须同时写入认证 username 到 `uploaded_by` 与 `raw_payload.normalized_payload.imported_by`，最终 session delta 必须保持同值；当前 session 读取和放弃使用同一已登记共享任务与服务端 provenance 事实；未登记草稿仍校验本人。session/file/batch/canonical candidate ID 使用带业务前缀的 UUID，不使用进程内顺序号或“先查询再递增”的多 worker 竞态分配。

file/session preview/retry 只允许通过当前 `session_id` 持久化该 session、files 与其 `preview_batch_id` 的精确 delta，且不得携带 canonical `invoices` / `transactions`；不得把进程内其它历史 session/batch 的 snapshot 写回 PostgreSQL。preview 的 `suspected_duplicate` 可保留候选 invoice 引用作为复核证据，confirm 后 terminal row 必须清空该非权威引用；`created`、`status_updated`、`duplicate_skipped` 的正式引用保持不变。发票 confirm 必须在同一事务内锁定本批强身份命中的 canonical 发票、持久化所选 session / batch / invoice delta，并只对本批身份集合式读取当前 OA attachment cache；命中强身份和明确 OA 子付款项时合并 OA 来源边，以 OA 来源替换当前人工来源/人工明细归属，保留独立 ETC 来源及原导入 batch / row 历史，再在同一事务标记必要的 Workbench matching scope。`disabled` promotion mode 不合并 OA 来源；其它模式在本批 canonical 已存在后只允许 link-existing，不得借此创建 cache 中其它发票。持久化或来源合并失败时 batch、file/session、canonical invoice、来源边和 matching dirty 必须整体回滚，领域任务不得半发布。普通 confirm 不发布 tax/read-model refresh。

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
- Page Audit：`imports.invoices` 是 direct-canonical 页面；在同一 repeatable-read read-only snapshot 内证明 file/session/batch/row、canonical invoice、`manual_invoice_import` source-link 与本页 canonical import job。
- 重复导入名称审计：已有正式 owner 的 `duplicate_skipped` 行不拥有名称覆盖权。仅在强身份、购销双方税号相同且原正式 owner 来源边完整时，购方/销方/对方名称差异报告 `invoice_import_duplicate_name_difference` warning，保留双方原值；新建、更新、首次正式化、身份/税号/金额及来源边不一致仍为 error。混合 created/updated 的同票明细组件不适用重复名称语义。审计不写数据，也不改变导入或关联接口。
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
- 普通发票 XLS/XLSX 与银行文件共享签名、容器资源上限与原件 SHA-256 完整性校验；同内容重传仍解析逐项查重。

## Canonical facts ownership

- Owned facts: `app.invoices` 的导入正式化事实，以及对应 `app.import_batches`、`app.import_batch_rows`、`app.import_files`、`app.file_objects` 中的发票导入事实。
- Allowed writes: invoice import preview/confirm/job、`ImportNormalizationService`、受控 OA/ETC 现有发票 link/promotion adapter。
- Allowed reads: invoice import facts repository、发票查询/context ports、owner API。
- Downstream outputs: invoice lifecycle、pending invoice、input/output invoice usage、OA pending、tax、cost 直接读取 canonical facts；`workbench`、`workbench_relation` 按自身访问/maintenance 合同使用精确 dirty scope。
- Forbidden paths: production API/worker 不得从 full snapshot、local pickle、`state:imports`、`state:full_state` 或 OA/ETC cache 直接构造第二发票池。
- Old code deletion: 旧同步导入、直接状态写入、snapshot 发票池 fallback、已确认 batch 撤销链和从 `app.import_files.import_batch_id` 反推 file session 状态的 fallback 已删除；仅保留 owner 校验后对未确认 preview 的显式放弃，该路径不触及 canonical invoice。
- Durable confirm：上传登记和 prepare job 原子受理，解析后进入 awaiting_confirmation；确认同一 job 的版本后进入 commit。无导入 outbox/RabbitMQ 前置依赖；queue 不可用返回 503。
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

## 右侧抽屉交互（2026-09-15）

本模块复用的右侧抽屉遵循[统一关闭行为](../../dev/right-drawer-dismissal.md)：外部点击/Esc 不关闭，X 继续执行已有关闭保护。业务 owner 持有保存/确认完成状态，公共 AppDrawer 仅展示 `completion`；不改变本模块后端 API、权限、事实写入及查询 I/O。旧的重复退出按钮和成功自动关闭路径已移除，内部编辑取消仍按局部职责处理。

## 2026-09-20 导入后的即时匹配

ConfirmedInvoiceImportUnitOfWork 在导入事务内继续提交 promotion 与同一 matching dirty scope；本入口 `debounce_seconds=0`，删除固定 60 秒等待。使用既有 expedite/processing 再变更去重语义；导入接口不运行归属算法，不写页面状态。后到的人工导入发票维持原 provenance，归属由 workbench owner 提交。

## 2026-09-20 OA 发票来源优先闭环

- 已有 OA 来源的后续人工/Excel 重复票只持久化导入历史，确认事务再次检查锁定后的 canonical 来源，禁止覆盖或追加人工边；纯重复不发布 matching dirty。
- 人工先到、OA 后到时保留 canonical ID、金额/核销/ETC 和原 source batch，替换当前人工来源与人工明细归属；导入页审计改由 terminal row 强身份证明 OA 接管后的历史引用。重复输入与 OA 值差异明示 warning，不改现存事实。
- migration 0172 仅清理已有混合来源与标签，保留财务列、导入历史，逐票审计 before/after，定向登记现有 matching scopes；重跑无更新。
- OA 来源审计在同一只读 SQL 内读取 completed `oa_applications/items/attachments` 与进行中 `oa_pending_payment_admissions.source_payload` 的结构化子项及附件；不能把进行中来源误报为无 OA。维护修复只按当前强身份、明确子项和真实附件 key 更新 OA 来源，并沿用 CAS、审计、同事务 matching dirty；不通过人工归属边补洞。

## 2026-09-21 凭证金额隔离

关联台凭证新增子项总金额，仍不创建或改写 canonical invoice，不计入发票张数、税额或抵扣。全局凭证 gallery 保持只读文件接口；外部“选择已有发票”按钮移除不改变关联台人工录入按强身份复用 canonical invoice 的合同。

## 2026-09-21 原始发票缺失核对

`import_audit_repair_ops --inspect-invoice-source --dry-run --file-id ... --invoice-id ...` 只读指定原始文件的“发票基础信息”表头和准确票号行，通过原 file object SHA 校验。拒绝混入执行/修复参数，不创建或修改发票。缺失发票仍须由普通导入预览、确认、job 形成正式事实；不能用 ETC 原始金额猜测税额。

## 2026-09-21 导入闭环变更

- 上传登记输出 `uploaded` session 与归档引用，不在请求中解析文件；登记草稿与 prepare job 同事务。worker prepare 保存逐项预览，并通过任务 completion 端口原子进入待确认。
- `ImportProcessingService` 的普通提交只传当前 selected scope delta、精确影响月份和结果；`ConfirmedInvoiceImportUnitOfWork` 先 `completion.lock(tx)`，最后 `completion.succeed(tx, result)`，成功与正式事实同事务。显式关联台同步补录仍复用领域事务，不要求异步任务。
- 当前 session 恢复通过 `load_file_import_session_snapshot(session_id)`，只读取本会话文件及其 batch/rows；相关现存发票/流水身份批量读取。不恢复全局历史 snapshot。
- `FileImportService.confirm_session` 始终原子确认所选范围，删除 `atomic_batch=False` 旧分支。任何错误/疑似行阻断该范围，未选文件保留草稿。确认后文件行与实际 batch 结果重新绑定，防止跨进程恢复后继续显示预览 created。
- 文件 SHA 仅用于原件完整性，不作业务去重。`find_confirmed_import_file_by_sha256` 端口与相同文件阻断已删除。每个业务项仍使用已有 invoice/bank identity 规则。
- 发票金额+税额与价税合计不一致、同强身份财务字段冲突明确报错，不能静默覆盖。20 位票号仅在“发票号码”列仍可识别；缺身份数据行、多非标准事实 sheet 或混合进销方向明确拒绝，不再忽略。
- 银行负借方+贷方字符串零（及对称负贷方情况）按真实冲正方向解析，保留银行 v3/v4 身份规则。
- 删除普通导入独立 background job 写入；任务和全局状态由 canonical import job 查询呈现。历史 outbox/background 仅保留取证读取，不构成执行入口。
- 直接回归：`tests/test_import_closed_loop.py`（含隔离真实 PostgreSQL）、`test_import_file_service.py`、`test_import_service.py`、`test_confirmed_invoice_import_uow.py`、`test_postgres_core_repository.py`、`test_postgres_state_store.py`。依赖及下游写权限未扩大。

### 登记失败、剩余范围与无动作闭环

- 原件先落不可变对象；`app.import_files`、preview session 与 prepare job 在一次事务登记。登记失败仅清理本次 UUID 原件且数据库证明未被任何 file/session/job 引用；响应丢失后已经提交的引用不得清理。
- 选择部分文件成功后，未选文件保持 preview_ready。携最新版本再次选择剩余文件创建新 commit 意图，复用 session 的原件和候选；旧任务不可变。重复任一已受理精确范围始终返回原任务。
- 纯银行强身份重复、无新增/更新/错误时 prepare 直接 succeeded + `outcome=no_changes`。发票重复仍可能补来源或元数据，不能按新增零机械判定无动作。
- 预览变更先 CAS 入 prepare 后由 worker 解析；放弃预览与 cancel job 同事务。确认前财务冲突将 awaiting_confirmation CAS 为 needs_review，用户重新预览后确认；同身份且同事实的并发新增仅重分类为重复。
- job 只保存 session 引用、范围、摘要和结果；候选明细只在 session/batch rows 存储。HTTP/worker request-local service 不重置全局实例。

### 已证历史财务拆分修复

`import_audit_repair_ops --repair-invoice-financial-source FILE_ID`（可重复）加精确 `--invoice-id` 是既有维护 CLI 的限定模式，不是新业务导入入口。它从已归档原件读取唯一“发票基础信息”，核对对象 SHA；所有目标必须唯一存在，日期、方向、价税合计不变，且原件明确给出未税金额、税额、合计。多个原件冲突、目标缺失、缺字段、SHA 漂移均停止，不反推税率。

先 `--dry-run` 查看逐票 before/after 与 source_fingerprint，再使用相同目标和 `--execute --expected-fingerprint ... --operator-id ... --reason ...`。在 serializable 事务内复核快照，通过 core repository CAS 修改财务字段及税务来源 provenance，精准失效包含这些身份的 OA 解析 cache；保留发票 ID、来源关系、核销关系与总额。数据库 fact guard 记录 before/after，维护操作审计与修改同事务。再次 dry-run 必须零财务更新、零待失效 cache。工具不创建数据库备份或删除数据库。

历史缺失导入审计行只能使用原有 row_results、normalized_rows 与明确 link 恢复可证部分；当前事实存在不证明当年是 created 还是 duplicate。证据不足的缺口保留并报告，不能写虚构成功记录让 Audit 变绿。

## 2026-09-21 确认前复核拒绝的审计分类

明确的 `selected files require review before confirmation: ...` commit 失败，只有所选文件全部存在、同属本会话、仍为 preview_ready、无正式 batch_id、对应预览批次仍 pending，且存在 error_count/suspected_duplicate_count 时，报告可见 warning `invoice_import_job_review_required`。其他任务失败、孤立引用、已提交/终结状态异常仍为 error。审计只读，不修改任务状态、导入行或正式发票；沿用输入错误不阻断全站的现有合同。`test_uncommitted_review_rejection_is_visible_warning_only` 覆盖正向与七种反向证据。

## 2026-09-21：人工识别共用的身份提取修复

`POST /imports/invoices/manual/recognize` 的请求、响应白名单和权限不变。共用附件解析器现在按 PDF 位置/OCR 同行坐标读取标签对应的票号，缺少票号标签时不从银行账号、校验码等数字猜测身份；无法识别时继续走现有人工填写反馈。税号不截断、不从未标注正文补齐。原生 PDF 识别成功仍不运行 OCR，上传不保留文件、不产生 canonical 写入。

## 2026-09-22 导入状态与恢复闭环

导入状态查询以 canonical import job + 已选文件类型投影归属，失败只影响实际业务域，不被映射成刷新。确认前复核拒绝使用 ImportReviewRequiredError，worker 转 needs_review；显式重新预览后仍需用户确认。历史相同复核拒绝保留 failed，显式重试走 prepare，不直接重跑 commit。只读审计与历史事实不改写；未处理警告不自动确认或删除。

实施和验收见 [修复计划](../../dev/import-runtime-status-repair-plan.md)。

## 2026-09-22 管理员导入任务处理

管理员 GET /api/imports/jobs（page/page_size）、GET /api/imports/jobs/{uuid}（file_page）只读；POST /api/imports/jobs/{uuid}/dispose 接受 version/action/reason/note，actor/request_id 来自认证请求。failed close 保留 failed/last_error，needs_review discard 同事务终结预览并 canceled；result_payload.disposition 与 acknowledged_at、版本和领域审计原子提交。与普通确认已知区分，明确处置任务禁止 confirm/reprepare/retry/cancel 重新激活。此处创建人/管理员限制已由下述共享导入任务合同替代；未登记私人草稿仍隔离。

实施、验证与旧链路清理见[处理闭环](../../dev/import-task-disposition-plan.md)。

## 2026-09-23 共享导入任务

银行、发票和 ETC 的已登记 durable import task 向所有已获平台访问权的登录用户开放查看、复核、重新预览、重试、确认和结束处理；不按创建人或管理员分层。未登记的私人草稿继续校验创建人；OA、税务和其他任务保留原权限。原页面权限、App Health 管理权限、设置和现金边界不扩大。

- 输入：`GET /api/imports/jobs?page&page_size&domain`、按任务 UUID 读取详情/银行映射、既有 session/review/confirm/retry/discard API。session 访问必须由同一 durable task 的类型、session ID 和原创建人事实证明；没有 task 时仅允许原草稿本人。`domain` 在分页与计数之前筛选，详情按需读取。
- 输出：共享任务摘要与分页详情、既有预览/任务 DTO、状态变化与真实操作人审计。创建人与文件 provenance 不修改；确认/重试的 actor 快照随任务持久化，worker 按实际操作人的当前平台授权执行，成功结果和领域审计与事实同事务。
- 前端：全局状态、银行/发票/ETC 页和 App Health 复用 `ImportJobDiagnostics`；共享抽屉复用 `ImportWorkflowPage` 的任务模式，不要求进入受页面 ACL 限制的原页。正常上传页仍为空白草稿；打开共享任务使用独立组件实例，不覆盖当前未保存内容。
- 刷新：沿用现有全局轮询，写后回读当前任务/列表；共享任务跨状态保持可见。不新增定时器、缓存、read model、队列、依赖、迁移或备份。
- 旧链清理：删除导入任务 admin-only、共享任务 creator-only、跨用户无法继续预览文案与对应旧测试假设；非共享任务的 owner 校验保留。失败不能用普通已读绕过明确结束处理；原错误历史保留。
- 验证：共享权限、私人草稿隔离、跨用户确认/异步审计、分页筛选、并发与回滚、丢失响应核实、旧页面导入回归；见[共享实施与验收](../../dev/import-task-disposition-plan.md#共享处理修订2026-09-23)。
