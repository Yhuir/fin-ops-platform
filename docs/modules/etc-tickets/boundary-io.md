# ETC票据管理模块边界与 I/O

日期：2026-07-18

## 模块化状态

- 状态：close
- 当前边界可信度：high
- 目标边界：ETC 票据页面和导入/修复服务通过 ETC application/reconciliation services 处理业务，关联影响通过 workbench relation 和 derived lifecycle 扇出。
- 当前缺口：页面/API 与 App 内部 Audit 证明主链路已闭环；对象存储文件字节、ETC 外部归档与真实 OA 草稿状态仍属于外部 gate。结果未知的 OA 创建只能由管理员带核实证据恢复。历史 repair/migration/backfill 工具作为显式运维入口保留，必须继续 dry-run/owner/allowlist 管控，不得进入常规页面链路。
- 旧代码删除条件：已删除 legacy `/api/etc/batches*`、ETC OA 自动检测 refresh、invoice-id 级 `/api/etc/invoices/revoke-submitted` 回退入口及测试 mock 假后端；历史 ETC migration/repair 工具在完成生产迁移职责且无生产/测试引用后再单独删除。

## 职责边界

### 负责

- ETC 票据管理页面、ETC 发票/批次、识别、对账、OA 草稿后批次发票 PDF 合并下载、历史批次修复。
- ETC 与发票附件、关联台候选之间的业务转换。
- 通过 lifecycle 触发 workbench/invoice/search 相关刷新。

### 不负责

- 不直接拥有 workbench relation 事实源。
- 不直接维护 pending invoice 或 tax offset read model。
- 不在导入流程外绕过 ETC service 写批次。

## 输入 I/O

| 输入 | 来源 | 合同 |
| --- | --- | --- |
| 页面查询/操作 | `EtcTicketManagementPage.tsx`、`features/etc/api.ts` | 进入 ETC routes/services；批次列表只按 `unsubmitted/staged/submitted` bucket、车牌、关键词走 PostgreSQL 窄 summary 查询；选择一个 business batch 后只读取一次精确 batch detail 和绑定 task，不调用 full reconciliation task list，不把详情数组塞入列表 DTO |
| OA 草稿 command | `POST /api/etc/business-batches/{id}/oa-draft`、`.../oa-draft/recover` | create 请求携带稳定 idempotency key；prepare 在 ETC 锁内持久化 attempt，OA HTTP 在锁外执行，finalize 通过 `save_etc_oa_draft_attempt` 对单一 business batch 做 version CAS 并只合并该 attempt 改动的 business batch/submission/invoice/import 行；同 key 或同 recovery 结果重放只补齐 linked task 的 OA 元数据，不再次创建 OA 草稿。结果未知禁止自动重试；recover 仅管理员可用，布尔决定必须是严格 JSON boolean，并提供 reason/evidence 与互斥的采纳/未创建证据 |
| 批次标题编辑 | `EtcTicketManagementPage.tsx`、`PATCH /api/etc/business-batches/{id}` | 只允许未提交 business batch 修改 `title`；请求带 `expectedVersion`，后端持久化 business batch title 并同步 linked reconciliation task title |
| 信用卡账单 PDF | `POST /api/etc/reconciliation-tasks/{task_id}/credit-card-statement`、`CcbCreditCardStatementParser` | 先落 source file 元数据，再从可选文字解析交易行；无可用交易行时才按页渲染并用布局 OCR 重建表格行。OCR 结果附带人工核对 warning；两种路径都输出同一 `FileParseResult`/`CreditCardItem` 合同。解析提交与 source file 删除互斥；OCR 期间源文件已删除时返回 HTTP 409 / `source_file_deleted_during_parse`，不得生成孤儿明细。 |
| ETC 发票导入/识别 | imports/services/parsers | 输出批次、任务、附件识别结果 |
| ETC invoice list | `GET /api/etc/invoices` | 只读查询入口；route owner 只接收 `etc_service`、`json_response`、`serialize_invoice` 三个读侧端口，不接收 JSON body、link refresh 或状态回退端口 |
| OA 草稿后发票 PDF 下载 | `GET /api/etc/business-batches/{id}/invoice-pdf` | 使用 read session；application service 校验 actor scope、OA 草稿和 `business_batch.invoice_ids`，再把发票元数据与 `EtcService.read_invoice_pdf_bytes` 读取端口交给 PDF bundle service；不直接读取 HTTP cookie/header，不写业务状态 |
| 历史修复/迁移 | tools | 只作为显式运维入口 |
| 页面 Audit | `GET /api/operations/app-health/page-audit?page=etc-tickets` | 管理员只读；同一 `REPEATABLE READ READ ONLY` snapshot 直接读取 canonical tables，不创建或刷新 read model |

## 输出 I/O

| 输出 | 目标 | 合同 |
| --- | --- | --- |
| ETC ticket/batch payload | 前端页面 | summary DTO 只含列表展示、三 bucket counts 和统一 `createOaDraftAction`；不含 invoice IDs、import attempts、audit events 或 task 嵌套详情。detail DTO 才包含当前业务批次明细 |
| Worker 持久化后的查询可见性 | ETC 票据/导入页面 | PostgreSQL 模式的 task、business batch、invoice 查询在读取前重载正式 snapshot，保证独立 import worker 的完成结果无需 API 重启即可见；file/memory backend 保持原有进程内语义 |
| ETC 发票合并 PDF | 浏览器下载 | `application/pdf`、RFC 5987 UTF-8 文件名、`private, no-store`；按开票日期/发票号/ID 稳定排序，每张发票恰好贡献一页；任一来源不可读、损坏、hash 不一致或不是单页时整包失败；成功记录 `etc_invoice_pdf_bundle_downloaded` 审计，不新增批次状态或 read model |
| linked reconciliation task title | ETC 发票导入 ready task 下拉 | business batch title 更新后同步 task title，导入页下拉展示最新批次标题 |
| 关联候选/关系影响 | workbench relation/lifecycle | 不直接写下游 read model |
| 修复/迁移结果 | 运维工具 | 可审计、可回滚或可重复 |
| Completed import job consumption | background job progress / operation barrier | ETC 发票导入 job 完成后，页面必须读取 job `operation_barrier_targets`，等待 targets fresh 后再刷新批次和任务列表 |
| Audit proof report | 统一页面 Audit UI | 输出 canonical expected-set、结构化展示字段、批次/任务/文件/发票/导入/提交内部 typed edge、统一发票桥和 durable import queue 证明；不宣称 shared Workbench relation 或外部 ETC/OA 完整性 |

## 持久化与投影

- Own read model：无独立 manifest entry。
- 页面 Audit：`etc-tickets` 是直接 canonical 页面，registry 的 `read_model_keys=()`；UI 只有在统一 Audit 返回 `integrity=pass / freshness=fresh / queue=drained`、正式数据库快照和 versioned ready contract 时才显示通过。Audit 额外证明三 bucket 互斥/计数同口径、creating attempt 完整且不超过 15 分钟、pending draft/submission 完整、submitted/not-submitted 占用闭合。只有 import job 的 `pending/processing` 属于 backlog；`failed/dead_lettered` 是终态，若其精确关联的 reconciliation task 已 `imported/closed`，页面审计把它计入 `covered_failed_import_job_count` 而不阻断，否则报告 terminal integrity failure。下游影响 read model 不得冒充页面消费模型。
- 影响 read model：`workbench`、`workbench_relation`、`invoice_lifecycle`、`search` 等。
- ETC 导入完成消费会额外等待 `tax_offset`、`input_invoice_usage`、`pending_invoice`、`oa_pending_payment`、`cost_statistics` 等 job result targets。
- Worker：通过 import/runtime handler、derived lifecycle 和 registered workers 扇出。
- PostgreSQL formal file rows：active task 每次保存时把不再存在于 task `source_files` 的 `app.etc_reconciliation_files` 行标记为 `deleted`；仍存在的文件继续 upsert 为 `stored`。formal rows 不得让已删除来源在重启后复活。
- PostgreSQL query consistency：ETC 页面 list/detail 必须使用 state store/repository 的窄读合同直接读取 worker 最新正式行；不得在热路径调用 `load_etc_state/load_etc_reconciliation_state` 全量 hydrate，也不得在 list/detail 探测对象存储。file/memory backend 使用同一合同的现有 snapshot 实现。
- OA attempt write consistency：OA prepare/finalize/fail/unknown/recover 只允许通过 state store 的 target-scoped CAS I/O 写目标 attempt；禁止用进程内全量 snapshot 覆盖其它批次或独立 worker 的更新。对账任务 OA 元数据是第二个明确 owner write；若它在 business batch 已提交后失败，相同 idempotency key/recovery evidence 必须可安全重放并收敛。

## 文件范围

| 层 | 文件或目录 |
| --- | --- |
| Frontend page | `web/src/pages/EtcTicketManagementPage.tsx` |
| Frontend feature/components | `web/src/features/etc/*`、`web/src/components/workbench/CandidateGroupGrid.tsx` |
| Backend route | `routes_etc.py`、`routes_etc_import.py`、`routes_etc_invoices.py`、`routes_etc_reconciliation.py` |
| Backend service | `etc_service.py`、`etc_business_batch_application_service.py`、`etc_invoice_pdf_bundle_service.py`、`etc_document_parsers.py`、`etc_reconciliation_*`、`invoice_attachment_recognition_service.py` |
| Audit proof owner | `services/postgres_repositories/etc_tickets_page_audit.py`、`services/page_audit_registry.py`、`services/postgres_repositories/operations_audit.py` |
| Workbench integration | `workbench_sql_projection.py`、`workbench_pair_relation_service.py`、`workbench_relation_command_service.py` |
| Tools | `cleanup_orphan_etc_reconciliation_tasks.py`、`migrate_historical_etc_business_batches.py`、`link_existing_etc_batches.py` |
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
- `tests/test_import_processing_service.py`
- `tests/test_audit_etc_tickets_read_model_tool.py`
- `tests/test_page_audit_registry.py`
- `tests/test_app_health_api.py`
- `web/src/test/EtcTicketManagementPage.test.tsx`
- `web/e2e/etc-tickets-flow.spec.ts`

## 当前缺口和删除条件

- 历史 migration/repair service 必须保留删除条件。
- ETC 变更必须检查 workbench candidate 和 invoice lifecycle fan-out。

## Canonical facts ownership

- Owned facts: `app.etc_invoices`、`app.etc_import_sessions`、`app.etc_import_batches`、`app.etc_submission_batches`、`app.etc_business_batches`、`app.etc_reconciliation_tasks`、`app.etc_reconciliation_files`、`app.historical_etc_repair_*`、`app.etc_batch_invoice_links`。
- Shared facts: `app.invoices` 由 canonical invoice pool owner 管理；ETC 只能通过受控 link/promotion port 关联。
- Allowed writes: ETC import service/job、business batch service、reconciliation service、受控 historical repair/backfill tools。
- Allowed reads: ETC business batch API、ETC services、canonical invoice existing-link ports。
- Downstream outputs: workbench、workbench_relation、tax/cost/search dirty scopes 或 owner producer 输出。
- Forbidden paths: legacy ETC batch pickle、OA detection metadata 或 ETC invoice rows 不得替代 canonical invoice pool；ETC repair 不得绕过 relation command service。
- Audit I/O boundary: Audit repository 只允许只读查询和 repeatable-read transaction；不得调用 ETC service mutation、refresh gateway、worker ack/retry、对象存储下载或 Workbench relation refresh。`app.workbench_pair_relations` 不是 ETC 页自己的 pairing source。
- Old code deletion: 生产主链路的 legacy `/api/etc/batches*` source-of-truth fallback、route owner、read facade、delete/lifecycle service、前端测试 mock 假后端和后端兼容测试已删除；页面 full task list、双 selection owner、重复 detail effect、task-row/task-delete UI 私链和对应 CSS 已删除。正式 reconciliation/import/source-file API 保留为 workflow 合同。ETC 专用 `oa-status/refresh` 和 invoice-id 级 `/api/etc/invoices/revoke-submitted` 回退入口已删除，并由 static guard 防回归。historical repair/backfill 工具保留不算页面/API closure 阻断，仍需按工具 owner/dry-run/deletion 条件单独收口。

## Phase 19 deterministic graph repair（2026-07-12）

- migration 0101 只从 submitted/closed business batch 的现有 `task_id/scope/title` 创建缺失的 imported reconciliation task，并把 batch title 对齐 task title；migration 0103 会从同一正式行的 typed `created_at/updated_at` 补齐 0101 遗漏的 normalized payload 时间戳，不能改写 task status、version、scope 或 typed 时间列。
- active ETC invoice 若指向已删除/不可见 business batch，则清除该 orphan owner，并把已有 canonical `batch_id` 写入 normalized `import_batch_id`；不创建新 invoice 或外部来源事实。
- task `source_files` 只从 `app.etc_reconciliation_files` 正式行重算；禁止从 payload 猜测文件、hash 或字节。
- ETC import batch 的 `invoice_ids` 是不可变导入尝试成员；同一 invoice 可因补附件/重复导入出现在多个历史 batch，而 invoice `import_batch_id` 仍指向首个/当前 provenance owner。Audit 分别证明“batch 成员全部存在”和“当前 owner 反向声明该 invoice”，禁止恢复错误的一对一 owner equality。
