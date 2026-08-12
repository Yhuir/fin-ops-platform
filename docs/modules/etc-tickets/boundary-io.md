# ETC票据管理模块边界与 I/O

日期：2026-08-02

## 页面完整性统计合同

- ETC 批次列表既有主响应增加 `statistics`，统计来自该页面查询所用的 ETC 发票、业务批次、对账任务和 OA 草稿事实；它不读取统一事实源汇总，也不受当前用户的 bucket、车牌、关键词或分页条件影响。
- ETC 页面当前直接读取 PostgreSQL canonical facts，没有 read model freshness 状态；统计、三个 bucket 计数和当前分页 items 的两条有界 SQL 必须在同一个显式 `REPEATABLE READ READ ONLY` 快照内执行，避免并发写入导致同一响应自相矛盾。业务批次状态与 OA 草稿数复用一次 `FILTER` 聚合；发票总数与已导入数单次扫描发票表，并通过发票持久化的导入来源标量关联有效导入批次，不在请求期展开批次 JSON 数组。不新增 endpoint、表、worker、缓存或第二套事实源。
- Page Audit 独立重算同一页面边界的统计并检查批次/发票/任务关系；页面统计只用于与外部统一事实源进行人工完整性对比，统一事实源不能反向填充页面统计。

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：ETC 票据页面和导入/修复服务通过 ETC application/reconciliation services 处理业务；普通写只提交 canonical facts/version/audit，受影响页面在访问时精确收敛，不通过 derived lifecycle 扇出页面重建。
- 当前缺口：页面/API 与 App 内部 Audit 证明主链路已闭环；对象存储文件字节、ETC 外部归档与真实 OA 草稿状态仍属于外部 gate。结果未知的 OA 创建只能由管理员带核实证据恢复。历史 repair/migration/backfill 工具作为显式运维入口保留，必须继续 dry-run/owner/allowlist 管控，不得进入常规页面链路。
- 旧代码删除条件：已删除 legacy `/api/etc/batches*`、ETC OA 自动检测 refresh、invoice-id 级 `/api/etc/invoices/revoke-submitted` 回退入口及测试 mock 假后端；OA create/replay/revoke/manual-status 中旧整批 canonical relink 已删除。历史 ETC migration/repair 工具在完成生产迁移职责且无生产/测试引用后再单独删除。

## 职责边界

### 负责

- ETC 票据管理页面、ETC 发票/批次、识别、对账、OA 草稿后批次发票 PDF 合并下载、历史批次修复。
- ETC 与发票附件、关联台候选之间的业务转换。
- 返回精确 affected scopes；保留的 workbench/relation read model 在 route 进入/重进、查询变化、浏览器手动刷新或明确重试时通过各自 owner 刷新，direct-canonical 页面直接读取已提交 facts。

### 不负责

- 不直接拥有 workbench relation 事实源。
- 不直接维护 pending invoice 或 tax offset read model。
- 不在导入流程外绕过 ETC service 写批次。

## 输入 I/O

所有 ETC import/reconciliation/business-batch unsafe route 必须先通过 mutation guard。对账任务的 `created_by`、source upload、patch、confirm、reopen、delete 与 cleanup actor 全部由已认证 session username 注入；JSON/form 中的 `actor`、`createdBy` 只作为废弃输入忽略，不得进入审计或持久化身份。

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/操作 | `EtcTicketManagementPage.tsx`、`features/etc/api.ts` | 进入 ETC routes/services；页面批次列表只发送 `unsubmitted/staged/submitted` bucket 与服务端分页，固定 `page_size=50`，消费 `pagination.page/pageSize/total`，bucket 切换回第 1 页，超过最后一页时回退有效末页；不提供月份、车牌或关键词搜索框。列表、counts、statistics 和 pagination 以同一次服务端响应为事实源，旧 `{bucket,page}` 请求不得晚到覆盖新查询，不允许本地 prepend/filter/count 算术伪造跨 bucket 状态。后端可选 `month/plate/keyword` 参数作为兼容/运维查询合同保留。选择一个 business batch 后只读取一次精确 batch detail 和绑定 task；重复点击当前 batch 是零状态写、零网络 I/O 的幂等操作，不得清空 detail/task；只有切换到不同 batch 才同步失效旧详情并并发读取新 detail/task。不调用 full reconciliation task list，不把详情数组塞入列表 DTO。task mutation target 必须同时满足“已加载 task ID = 当前选中 business batch 的 task ID”；bucket/页切换或刷新响应自动迁移 selection 时必须同步失效旧 task，禁止旧 task I/O 泄漏到新批次。四阶段进度只读取当前 batch/task 内存事实，网络、持久化与全局 listener I/O 均为零 |
| OA 草稿 command | `POST /api/etc/business-batches/{id}/oa-draft`、`.../oa-draft/recover` | create 请求携带稳定 idempotency key；prepare 在 ETC 锁内持久化 attempt，OA HTTP 在锁外执行，finalize 通过 `save_etc_oa_draft_attempt` 对单一 business batch 做 version CAS 并只合并该 attempt 改动的 business batch/submission/invoice/import 行；同 key 或同 recovery 结果重放只补齐 linked task 的 OA 元数据，不再次创建 OA 草稿。结果未知禁止自动重试；recover 仅管理员可用，布尔决定必须是严格 JSON boolean，并提供 reason/evidence 与互斥的采纳/未创建证据。历史 creating 行若缺 prepared submission，只能在权威 OA 查询为零后确认未创建并 CAS 回未提交 bucket；禁止采纳草稿或创建伪 attempt。OA draft create/replay/recover 不读取/写入 canonical invoice link，也不触发下游 read model |
| OA 草稿预填配置 | `GET/PUT /api/workbench/settings/oa-draft-prefill/etc` | 页面右上角 admin-only 抽屉读取/保存独立 versioned family；ETC prepare 原子保存当次配置快照和 session display name，锁外 OA I/O 不重读设置。申请日期和金额由当次创建动态填充；申请事由只显示业务文本，ETC/business batch ID 仅放结构化字段供同步识别 |
| OA 金额与发票金额展示 | linked reconciliation task `oaTotalAmount`、business batch `invoiceSummary`、`amountBreakdown` | `oaTotalAmount`/`amountBreakdown.oaAmount` 是 OA 提交金额事实源；`invoiceSummary` 的持久化标量只从 business batch `invoice_ids` 对应 ETC 发票求数量和含税总额，不得被 submission/OA `total_amount`、`oa_total_amount` 覆盖。列表与详情必须返回同一发票汇总；历史差额使用既有 `amountBreakdown.gapAmount/gapReason` 如实展示，不据差额自动补发票。所有金额以无千分位两位小数展示；差额只提示、不阻断、不写回；禁止为该展示新增共享 API、read model、queue 或跨页面写入 |
| OA 草稿结果决定 | `POST /api/etc/business-batches/{id}/manual-oa-status` | `submitted` 表示用户已在 OA 完成草稿提交，批次进入已提交；`not_submitted` 表示用户已在 OA 删除草稿，批次回到未提交。结果弹窗只暴露这两个 command，草稿打开/PDF 下载属于暂存区只读工具。该 command 只写 business batch / reconciliation task / audit 与精确 affected scope，禁止 relink canonical invoice，也不写后投递 Workbench/matching/Tax/Cost/history 页面 refresh |
| 批次列表标题 | `EtcTicketManagementPage.tsx` | 左栏仅展示 `created_at` 的用户可读时间，并在同一行展示发票数量和金额；不展示或编辑 internal business batch ID、external batch ID 或历史内部 title。后端 title/PATCH 合同只保留给现有非页面调用方。 |
| ETC 对账来源文件 | `untrusted_document_policy.py`、`etc_reconciliation_source_upload_service.py` | 在对象存储和解析之前统一校验后缀、文件签名、类型、字节数、图片像素/尺寸、PDF 页数/渲染像素和 DOCX 解压资源；票根只接受 TXT/PDF/JPG/PNG，信用卡账单只接受 PDF。签名与后缀不一致、未知二进制或超限文件返回 `invalid_document_upload`，不得再按 document fallback、写入 source file 或进入 OCR。 |
| 信用卡账单 PDF | `POST /api/etc/reconciliation-tasks/{task_id}/credit-card-statement`、`CcbCreditCardStatementParser` | 通过统一文件边界后，先从 PDF 文字层解析交易行；无可用交易行时才逐页渲染并用布局 OCR 重建表格行，不积压全部页面位图。OCR 结果附带人工核对 warning；两种路径都输出同一 `FileParseResult`/`CreditCardItem` 合同。禁止恢复外部 `pdftotext` 进程或 raw bytes OCR fallback。解析提交与 source file 删除互斥；OCR 期间源文件已删除时返回 HTTP 409 / `source_file_deleted_during_parse`，不得生成孤儿明细。 |
| ETC 发票导入/识别 | imports/services/parsers | 输出批次、任务、附件识别结果 |
| ETC invoice list | `GET /api/etc/invoices` | 只读查询入口；route owner 只接收 `etc_service`、`json_response`、`serialize_invoice` 三个读侧端口，不接收 JSON body、link refresh 或状态回退端口 |
| OA 草稿/已提交批次发票 PDF 下载 | `GET /api/etc/business-batches/{id}/invoice-pdf` | 使用 read session；application service 校验 actor scope，并要求存在 OA 草稿或批次属于 `ETC_BUSINESS_BATCH_SUBMITTED_STATUSES`；历史已提交批次不因缺少 `oa_draft_id` 被拒绝。成员只取 `business_batch.invoice_ids`，再把发票元数据与 `EtcService.read_invoice_pdf_bytes` 读取端口交给 PDF bundle service；不直接读取 HTTP cookie/header，不写业务状态 |
| 已提交批次附件恢复 | `POST /api/etc/business-batches/{id}/invoice-pdf/repair` | 仅管理员、仅 submitted 状态、仅 multipart 原始 ZIP；必须提交 `expectedVersion` 与 `reason`。已有 hash 的附件继续严格校验 SHA-256；只有附件路径/hash、导入来源全空且来源为 `canonical_invoice:*` 的历史后补成员可在强身份、单页 PDF 内发票号和 business/submission 成员一致校验后 bootstrap PDF/XML，并从原始 XML 纠正通行日期、车牌、车型、来源及提交批次汇总。对象先写、事实 CAS 持久化，失败恢复 preimage 并删除新对象；不创建发票、不改成员、不改 OA/配对/提交状态，重复执行返回零修复 |
| 历史修复/迁移 | tools | 只作为显式运维入口。单批次 tombstone 恢复必须同时核对业务批次 ID、版本、OA row、发票数量与含税总额，并通过 dry-run fingerprint 执行；canonical invoice link backfill 必须限定同一 business batch 且核对严格候选数。已提交批次成员缺失修复必须同时绑定 business/submission/external 三个 owner、精确 canonical 发票号与车牌、目标金额、结果数量/金额和当前 fingerprint；事务内复用 ETC invoice/link/overlap 边界，重算成员事实与审计，禁止修改 OA 草稿、关闭任务、附件或 Workbench 投影 |
| 页面 Audit | `GET /api/operations/app-health/page-audit?page=etc-tickets` | 管理员只读；同一 `REPEATABLE READ READ ONLY` snapshot 直接读取 canonical tables，不创建或刷新 read model |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| ETC ticket/batch payload | 前端页面 | summary DTO 只含当前页列表展示、三 bucket counts、全量 statistics、pagination 和统一 `createOaDraftAction`；页面 rail 的“批次数”展示 `pagination.total`，不是当前页 `items.length`，每行只显示创建时间、发票数量和金额。不含 invoice IDs、import attempts、audit events 或 task 嵌套详情。detail DTO 才包含当前业务批次明细 |
| Worker 持久化后的查询可见性 | ETC 票据/导入页面 | PostgreSQL 模式的 task、business batch、invoice 查询在读取前重载正式 snapshot，保证独立 import worker 的完成结果无需 API 重启即可见；file/memory backend 保持原有进程内语义 |
| ETC 发票合并 PDF | 浏览器下载 | `application/pdf`、RFC 5987 UTF-8 文件名、`private, no-store`；按开票日期/发票号/ID 稳定排序，每张发票恰好贡献一页；任一来源不可读、损坏、hash 不一致或不是单页时整包失败；成功记录 `etc_invoice_pdf_bundle_downloaded` 审计，不新增批次状态或 read model |
| ETC OA 附件引用 | OA form draft | `HttpEtcOAClient` 在上传响应边界把已知 OA absolute `/fileManager/` / `/profile/` URL 归一为根相对路径；已有相对路径与 opaque file id 保持不变，未知 absolute host/path fail closed。现有 payload builder 把同一规范值写入 `response.data` 与 `response.extra.filePath`，页面/Nginx 不做补偿拼接 |
| ETC OA 付款申请预填 | OA form draft | 使用已验证的 OA code 写入申请类型、支付方式、发票种类和项目 ID，并写入申请人、当天日期、批次金额、收款方、开户行、账号及模板渲染的申请事由；配置变更不改已 prepare attempt，重放保持原快照 |
| linked reconciliation task title | ETC 发票导入 ready task 下拉 | business batch title 更新后同步 task title，导入页下拉展示最新批次标题 |
| 关联候选/关系影响 | workbench relation/lifecycle | 不直接写下游 read model |
| 修复/迁移结果 | 运维工具 | 可审计、可回滚或可重复；恢复只写回原 tombstone 或精确缺失成员，不创建第二个业务批次，不直接写页面投影；成员修复完成后通过 historical ETC repair runtime port 执行 official lifecycle，并仅按共享消费者合同 enqueue 精确月份的 `workbench_relation`，不得投递已退役的 page `workbench` event 或 `all` scope |
| Completed import job consumption | background job progress / current page load | ETC 发票导入 job 完成后当前可见页执行一次普通 canonical GET；其它页面不被写后强制重建。 |
| 前端刷新提示 | `etcBusinessBatchUpdated` / `invoiceFactUpdated` | 事件仅允许刷新当前可见且订阅该领域的页面；hidden 页面忽略且不重放。事件不是 freshness 事实源，也不得触发其它页面重建 |
| Audit proof report | 统一页面 Audit UI | 输出 canonical expected-set、结构化展示字段、批次/任务/文件/发票/导入/提交内部 typed edge、统一发票桥和 durable import queue 证明；不宣称 shared Workbench relation 或外部 ETC/OA 完整性 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 页面 Audit：`etc-tickets` 是直接 canonical 页面，registry 的 `read_model_keys=()`；UI 只有在统一 Audit 返回 `integrity=pass / freshness=fresh / queue=drained`、正式数据库快照和 versioned ready contract 时才显示通过。Audit 额外证明三 bucket 互斥/计数同口径、creating attempt 完整且不超过 15 分钟、pending draft/submission 完整、submitted/not-submitted 占用闭合。not-submitted 批次保留的是历史成员；发票已由另一个可见批次合法接管时，旧批次不再要求它保持 `unsubmitted`，当前 owner 自己的 submitted/owner/submission 规则负责闭合。只有 import job 的 `pending/processing` 属于 backlog；`failed/dead_lettered` 是终态，若其精确关联的 reconciliation task 已 `imported/closed`，页面审计把它计入 `covered_failed_import_job_count` 而不阻断，否则报告 terminal integrity failure。下游影响 read model 不得冒充页面消费模型。
- 影响消费者：关联台 direct canonical API、`workbench_relation` 以及 invoice lifecycle、税金、成本等 direct-canonical 页面；关联台页面自身没有 refresh consumer。
- ETC 导入逻辑上影响 `tax_offset`、`input_invoice_usage`、`pending_invoice`、`oa_pending_payment`、`cost_statistics` 等页面，但普通完成结果不携带这些 barrier targets；页面访问时自行收敛。
- Worker：import/runtime handler 只负责 durable 领域任务；ETC 页面没有 read model
  worker、freshness gateway 或页面 refresh request。
- PostgreSQL formal file rows：active task 每次保存时把不再存在于 task `source_files` 的 `app.etc_reconciliation_files` 行标记为 `deleted`；仍存在的文件继续 upsert 为 `stored`。formal rows 不得让已删除来源在重启后复活。
- PostgreSQL query consistency：ETC 页面 list/detail 必须使用 state store/repository 的窄读合同直接读取 worker 最新正式行；不得在热路径调用 `load_etc_state/load_etc_reconciliation_state` 全量 hydrate，也不得在 list/detail 探测对象存储。file/memory backend 使用同一合同的现有 snapshot 实现。
- OA attempt write consistency：OA prepare/finalize/fail/unknown/recover 只允许通过 state store 的 target-scoped CAS I/O 写目标 attempt；禁止用进程内全量 snapshot 覆盖其它批次或独立 worker 的更新。对账任务 OA 元数据是第二个明确 owner write；若它在 business batch 已提交后失败，相同 idempotency key/recovery evidence 必须可安全重放并收敛。local state store 保存失败时，`record_oa_draft_created` 必须在抛错前回滚 task version、OA metadata、audit event 和 audit counter，重试成功后跨实例只能观察到一次 durable 审计。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/EtcTicketManagementPage.tsx` |
| Frontend feature/components | `web/src/features/etc/*`、`web/src/components/workbench/CandidateGroupGrid.tsx` |
| Backend route | `routes_etc.py`、`routes_etc_import.py`、`routes_etc_invoices.py`、`routes_etc_reconciliation.py` |
| Backend service | `etc_service.py`、`etc_business_batch_application_service.py`、`etc_invoice_pdf_bundle_service.py`、`etc_document_parsers.py`、`etc_reconciliation_*`、`invoice_attachment_recognition_service.py` |
| Audit proof owner | `services/postgres_repositories/etc_tickets_page_audit.py`、`services/page_audit_registry.py`、`services/postgres_repositories/operations_audit.py` |
| Workbench integration | `workbench_canonical_rows.py`、`workbench_pair_relation_service.py`、`workbench_relation_command_service.py` |
| Tools | `cleanup_orphan_etc_reconciliation_tasks.py`、`restore_deleted_etc_business_batch.py`、`backfill_etc_batch_invoice_links.py`、`repair_submitted_etc_batch_members.py`、`repair_etc_business_batch_summary.py`、`services/postgres_repositories/submitted_etc_batch_member_repair.py`；删除批次恢复、已提交批次成员修复或汇总标量修复都必须先 dry-run 并绑定 owner/version/fingerprint。汇总修复只在 raw/formal 成员集合完全一致时按实际 ETC 成员重算数量/金额并写审计，不改成员、OA 或 relation。成员修复只补精确 canonical invoice facts/link，归一化 business/submission 统计并通过 tool runtime port 触发既有 historical ETC lifecycle；该 port 只为真实共享消费者投递精确月份的 `workbench_relation` refresh，关联台页面下一次 normal GET 直接读取已提交事实 |
| Tests | `tests/test_etc_*.py`、`web/src/test/Etc*.test.*`、`web/e2e/etc-tickets-flow.spec.ts` |

## 依赖方向

- 允许依赖：ETC parsers, invoice attachment recognition, workbench relation, derived lifecycle。
- PDF 下载允许依赖：现有 PyMuPDF 合并能力与 `EtcService` 文件字节读取端口；对象存储 key、MinIO client 和 HTTP response 不得进入 PDF bundle service。
- 必须通过：ETC application/reconciliation services。
- 禁止绕过：修复工具直接成为常规业务写路径；页面直接操作历史批次状态；任何代码重新暴露 legacy `/api/etc/batches*`、`/api/etc/business-batches/{id}/oa-status/refresh` 或 `/api/etc/invoices/revoke-submitted`。

## 测试与验证

- `tests/test_etc_backend.py`
- `tests/test_etc_invoice_pdf_bundle_service.py`
- `tests/test_etc_reconciliation_service.py`
- `tests/test_repair_etc_business_batch_summary_tool.py`
- `tests/test_import_processing_service.py`
- `tests/test_audit_etc_tickets_read_model_tool.py`
- `tests/test_page_audit_registry.py`
- `tests/test_app_health_api.py`
- `web/src/test/EtcTicketManagementPage.test.tsx`
- `web/e2e/etc-tickets-flow.spec.ts`，以 121 个业务批次验证第 2/3 页、第 121 条和 `page_size=50`。

## 当前缺口和删除条件

- 历史 migration/repair service 必须保留删除条件。
- ETC 变更必须检查 canonical relation candidate、invoice lifecycle source version 与关联台首次 direct GET 结果；禁止恢复页面 refresh fan-out。

## Canonical facts ownership

- Owned facts: `app.etc_invoices`、`app.etc_import_sessions`、`app.etc_import_batches`、`app.etc_submission_batches`、`app.etc_business_batches`、`app.etc_reconciliation_tasks`、`app.etc_reconciliation_files`、`app.historical_etc_repair_*`、`app.etc_batch_invoice_links`。
- Shared facts: `app.invoices` 由 canonical invoice pool owner 管理；ETC 只能通过受控 link/promotion port 关联。
- Allowed writes: ETC import service/job、business batch service、reconciliation service、受控 historical repair/backfill tools。
- Allowed reads: ETC business batch API、ETC services、canonical invoice existing-link ports。
- Downstream outputs: 真实 ETC invoice delta 和 manual submitted/not-submitted 只返回精确 affected scopes/source versions；普通写不输出 workbench、workbench_relation、tax/cost 页面 dirty scopes。各页面访问时按 owner contract 收敛，Cost 保持两阶段访问收敛。
- Forbidden paths: legacy ETC batch pickle、OA detection metadata 或 ETC invoice rows 不得替代 canonical invoice pool；ETC repair 不得绕过 relation command service。
- Audit I/O boundary: Audit repository 只允许只读查询和 repeatable-read transaction；不得调用 ETC service mutation、refresh gateway、worker ack/retry、对象存储下载或 Workbench relation refresh。business batch 金额核对应使用 `amountBreakdown.etcInvoiceAmount` / `invoiceSummary.amount` 的实际 ETC 发票成员合计；OA 提交金额只允许作为无 ETC 汇总字段的 legacy fallback。存在明确 `partial` coverage 与 `gap_reason` 的 OA/ETC 差额不是发票集合损坏。`app.workbench_pair_relations` 不是 ETC 页自己的 pairing source。
- Old code deletion: 生产主链路的 legacy `/api/etc/batches*` source-of-truth fallback、route owner、read facade、delete/lifecycle service、前端测试 mock 假后端和后端兼容测试已删除；页面 full task list、双 selection owner、重复 detail effect、task-row/task-delete UI 私链、页面级 `plate/keyword` state/DOM/request 参数和旧筛选/卡片容器 CSS 已删除。正式 reconciliation/import/source-file API 以及后端可选查询参数保留为 workflow/兼容查询合同。ETC 专用 `oa-status/refresh`、invoice-id 级 `/api/etc/invoices/revoke-submitted`、OA workflow 的 `_link_existing_canonical_invoices(...)` 调用、无调用方 `etc_oa_submitted` / `etc_oa_revoked` lifecycle 和前端 batch+invoice 合并 emitter 已删除，并由 static guard 防回归。historical repair/backfill 工具保留不算页面/API closure 阻断，仍需按工具 owner/dry-run/deletion 条件单独收口。

## Phase 19 deterministic graph repair（2026-07-12）

- migration 0101 只从 submitted/closed business batch 的现有 `task_id/scope/title` 创建缺失的 imported reconciliation task，并把 batch title 对齐 task title；migration 0103 会从同一正式行的 typed `created_at/updated_at` 补齐 0101 遗漏的 normalized payload 时间戳，不能改写 task status、version、scope 或 typed 时间列。
- active ETC invoice 若指向已删除/不可见 business batch，则清除该 orphan owner，并把已有 canonical `batch_id` 写入 normalized `import_batch_id`；不创建新 invoice 或外部来源事实。
- task `source_files` 只从 `app.etc_reconciliation_files` 正式行重算；禁止从 payload 猜测文件、hash 或字节。
- ETC import batch 的 `invoice_ids` 是不可变导入尝试成员；同一 invoice 可因补附件/重复导入出现在多个历史 batch，而 invoice `import_batch_id` 仍指向首个/当前 provenance owner。Audit 分别证明“batch 成员全部存在”和“当前 owner 反向声明该 invoice”，禁止恢复错误的一对一 owner equality。
