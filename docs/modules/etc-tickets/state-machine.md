# ETC票据管理 状态机


> 修改 `ETC票据管理` 相关业务状态、UI 状态、read model 状态或 worker 状态前必须读取本文件。当前没有独立状态机时，在对应小节写明“不适用原因”，不要删除文件。

## 业务状态

- 当前状态：
  - `draft/.../imported/oa_draft_failed/not_submitted`：业务批次属于“未提交”。
  - `oa_draft_creating`：用户已发起草稿创建，属于“暂存”；prepare 已持久化，OA I/O 在业务锁外执行，等待用户按 OA 实际操作确认。
  - `oa_confirmation_pending`：OA 草稿 ID/URL 已持久化，同样属于“暂存”，等待用户人工确认。
  - `oa_submitted/manually_marked_submitted/closed`：用户确认 OA 已提交，业务批次进入“已提交”，绑定的 ETC 对账任务同步闭环。
  - `not_submitted`：用户确认 OA 未提交，释放本地 ETC 发票占用并回到未提交链路。
  - `deleted`：用户可见业务批次被删除。页面只从业务批次行发起删除；后端绑定 task 删除 API 仍作为正式 workflow/运维合同。已绑定正式 `oa_row_id` 的 submitted 批次禁止进入该状态；历史错误 reset 只能按原 tombstone 成员恢复。
- 状态事实源：`etc_business_batches` 业务批次、绑定的 ETC 对账任务状态、ETC 提交批次及审计事件。
- 允许流转：
  - 导入确认后创建或更新同一个业务批次，不在前端拆成“导入任务”和“对账任务”两个用户可见任务。
  - 用户点击“新建批次”时，由 `POST /api/etc/business-batches` 闭环编排创建 reconciliation task 和 active business batch，并返回统一业务批次 payload；前端不得先创建空 task 再把 task 当作批次显示。
  - 未提交业务批次允许通过 `PATCH /api/etc/business-batches/{id}` 修改 `title`，必须带 `expectedVersion` 防并发覆盖；标题更新写入业务批次审计，并同步 linked reconciliation task title。
  - 创建 OA 草稿必须按 `prepare -> execute external -> finalize` 执行并使用稳定 `idempotencyKey`；外部 I/O 不得持 ETC 业务锁。点击后 UI 立即进入暂存，附件在 adapter 边界以有界并发上传并保持稳定顺序。明确失败回到未提交；结果未知保持 creating 并禁止盲重试。
  - 普通页面不查询 OA、不要求草稿 ID/URL，也不展示 recovery 表单。`oa_draft_creating` 与 `oa_confirmation_pending` 都允许用户直接声明已在 OA 提交或已在 OA 删除草稿；决定由用户负责，App 只做版本 CAS、状态持久化和审计。管理员 recovery 仅用于历史/技术修复。
  - prepare/finalize/recovery 的 durable write 必须以目标 business batch 当前 version 为 CAS 前置条件，并只写当前 attempt 拥有的 business batch、submission batch 及确实发生变化的 invoice/import rows；不能回写全量旧 snapshot。business batch 已进入 `oa_confirmation_pending`、但 linked task OA 元数据写入失败时，相同 idempotency key 或相同 recovery 证据只执行修复写，禁止第二次调用 OA。
  - 暂存批次选择“我已在 OA 系统上完成 OA 草稿的提交”进入已提交；选择“我已在 OA 系统上删除该 OA 草稿”进入 `not_submitted`，清空 submission/draft 占用但保留批次、发票成员、源文件和核对数据。
  - 创建 OA 草稿后只能由 `manual-oa-status` 人工确认 `submitted` 或 `not_submitted`。
  - OA 草稿创建成功后，或 business batch 已进入 `oa_submitted` / `manually_marked_submitted` / `closed` 后，允许只读下载当前批次关联的 ETC 发票合并 PDF；历史已提交批次不要求补造 OA 草稿 ID。暂存区与已提交“发票明细”标题栏复用同一 API，下载不改变批次/折叠状态。`invoice_ids` 决定成员，稳定排序后每张发票必须恰好贡献一页，任一来源异常时整包失败。
  - 历史已提交批次若 PDF/XML 对象缺失，管理员可用原始 ZIP、当前版本和原因执行受限附件恢复。已有 hash 时只能写回完全一致内容；仅附件与导入来源全空、来源为 `canonical_invoice:*` 的历史后补成员，可在强身份、单页 PDF 发票号和 business/submission 成员一致校验后建立附件事实，并从原始 XML 纠正通行日期、车牌、车型和提交批次汇总。恢复不改变批次状态、成员、OA 或配对关系，失败必须回滚事实与新对象，重复执行必须幂等。
  - `submitted` 成功后，关联台 open 区生成一条 `source_kind=etc_invoice_summary` 折叠汇总发票行，金额取业务批次上报金额，等待未来 OA 和银行流水进入后普通配对。
  - 任意业务阶段允许删除本地批次记录；删除必须写入审计并校验 `expectedVersion` 防并发覆盖，但不得因 `importing`、`oa_draft_created`、`submitted_confirmed`、`closed` 等流程状态阻塞。
  - 删除未提交批次会清理本地导入批次、ETC metadata/附件关系和绑定任务；删除已提交批次会本地 reset 业务批次，释放 ETC 发票 `current_batch_id`，让 `etc_invoice_summary` 消失；只有原本已存在于统一发票池的发票才可能回到普通发票视图。
  - 绑定的 `etc_reconciliation_tasks` 删除后必须落为 `deleted` tombstone，而不是从内存 snapshot 中物理移除；列表、详情、ready-for-import 入口必须过滤 deleted task，但 tombstone 保留 task counter 和重启后的删除事实，防止 Postgres 只追加/更新式持久化在部署后重新加载旧 task-only 行。
  - 信用卡 PDF/票根文件上传先建立 source file，再执行解析；解析提交和 source file 删除必须互斥。若慢 OCR 完成前 source file 已被删除，解析提交返回 `source_file_deleted_during_parse`，不得把 `FileParseResult`、信用卡项或异常项写回任务。历史孤儿解析结果允许由同一 source file 删除入口按 `file_id` 清理并记录审计。
  - 已提交 `etc_invoice_summary` 若已经参与关联台 active relation，删除批次时必须取消包含该 summary row 的 active relation；取消后不得恢复历史 OA+银行流水二栏 active relation，OA 和银行流水各自回到未配对。
- 禁止流转：
  - ETC 页面不得提供自动 OA 检测、刷新检测或异常检测入口。
  - ETC 后端不得保留专用 OA 检测 refresh API、detector adapter 或 worker；批次已人工确认后不得被后台检测覆盖。
  - ETC 后端和前端不得保留 `/api/etc/invoices/revoke-submitted` 或 invoice-id 级直接回退 submitted 的入口；提交状态回退只能通过 business batch `manual-oa-status` / `oa-draft/revoke` / delete-reset 状态机完成。
  - 已提交、人工确认已提交或 closed 业务批次不得继续修改标题。
  - 关联台未找到 OA 和银行流水三项匹配前，`etc_invoice_summary` 不得直接进入已配对区。

## UI 状态

- loading：页面加载业务批次、导入/草稿/人工确认或合并下载动作执行中时显示按钮级 loading，不展示后台英文状态码作为主文案。
- empty：未提交或已提交 tab 下无批次时只显示该 bucket 的空态；一个业务批次在前端只出现一次。
- initial load：页面进入和刷新只能读取已有业务批次/对账任务，不得自动创建空 ETC 对账任务；新建批次只能由用户点击“新建批次”触发。
- batch list：左侧批次列表和 tab 计数只使用 `/api/etc/business-batches*` 的窄 summary 事实；页面不再提供月份选择器，默认展示全部用户可见批次并分“未提交/暂存/已提交”三个互斥 bucket；task-only active task 只允许出现在 workflow 内部状态或异常恢复入口，不得混入批次列表。
- workflow progress：页面按“准备核对资料 / 确认核对结果 / 导入 ETC 发票 / 提交 OA 审批”展示四阶段只读投影。`draft/reviewing/ready_for_import/importing/imported/OA creating/pending/failed/not_submitted/submitted/closed` 及失败、部分失败、迁移冲突必须映射为已完成、当前、处理中、待人工确认或需要处理；不得新增业务状态或把 `oa_confirmation_pending`、失败、回退伪装成已完成。
- amount contract：创建 OA 草稿前同时显示对账任务 `oaTotalAmount` 与业务批次实际 `invoiceSummary`。OA 草稿始终使用前者；两者差额只做非阻断说明。创建结果弹窗只保留两个状态决定按钮，不提供打开草稿或关闭按钮；Escape/遮罩仍可退出，暂存区继续提供打开草稿与下载 PDF。
- selection loading：用户切换批次时必须同步失效旧 task mutation target；新 batch 的精确 task 请求与 detail 请求并发发起。任一请求未完成时，旧 task 只能作为已清除状态，不能继续上传、删除、刷新匹配、确认或 reopen；人工状态变更由 active bucket effect 作为唯一 list reload owner。
- title editing：未提交 business batch 行的标题可点击内联编辑，Enter 或失焦保存，Esc 取消；保存失败保留错误提示，不伪装为已保存。已提交 bucket 不展示标题编辑入口。
- error：导入、创建草稿、人工确认、删除失败时显示本地化业务错误；内部对象 id、文件 id、旧检测码不作为主要用户文案。
- upload/delete conflict：上传仍在解析时若来源被并发删除，页面接收 HTTP 409 和“源文件在解析完成前已被删除，请重新上传”，不得显示上传成功；刷新后“已上传文件”和解析明细必须由同一组 source `file_id` 派生。
  - submitted delete confirm：仅尚无正式 OA 行的本地 submitted 批次允许 reset；已绑定 `oa_row_id` 时后端 fail fast。历史错误 tombstone 恢复为原 submitted 状态，重复执行不追加第二次恢复审计。
- OA sync safety：ETC 页面本身不触发 OA 自动检测；关联台独立读取 `/api/oa-sync/status` 作为写安全状态，不再展示 page read-model stale/refreshing。
- permission disabled/hidden：权限不足时隐藏或禁用创建、导入、草稿、人工确认入口；read-export 用户在 actor scope 内仍可下载 OA 草稿或正式已提交批次的发票合并 PDF；删除入口不做流程状态阻塞，后端只保留版本并发校验和本地清理一致性校验。

## Canonical 可见性 / Worker 状态

- ETC 业务批次列表直接读取业务批次事实源；关联台在同一 direct canonical GET 中由已提交 ETC business batch/links 构造 `etc_invoice_summary`，不读取 page projection。
- `submitted` 人工确认会隐藏散落 ETC 发票，并让 Workbench 未配对区在下一次 normal GET 显示一条合并行；关联台读取失败不得回滚已经提交的业务批次。
- `etc_invoice_summary` 与 ETC 页面金额统一显示无千分位的两位小数；关联台 direct descriptor/hydration 保留结构化金额，用于展示、金额搜索和过滤，禁止恢复 `workbench_rows` 物化字段。
- ETC 导入确认、OA 草稿创建、人工提交/未提交确认、业务批次本地删除/重置只提交 owner canonical facts；关联台下一次 normal GET 自然可见，不 enqueue page refresh。正式关系变化仍按 shared relation/matching 的独立合同处理。
- canonical invoice identity：ETC 发票有稳定发票号/强 `source_unique_key` 时，不得同时持久化弱 `data_fingerprint`；runtime worker 和 API 导入确认只能把 ETC metadata 关联到已存在的 canonical invoice，不得从 ETC 专用表创建 canonical invoice。
- 失败恢复：业务命令失败时通过正式 ETC/import job 重试；关联台 direct GET 失败只重试读取，不触发 rebuild。业务批次、ETC 发票占用和审计事实不得从前端临时修补。导入确认的同一 session 只有 queued/running 或近期 succeeded job 可复用；failed、acknowledged、cancelled 等旧 job 必须允许重新确认并创建新 job。
- 生产残留清理：若历史部署已留下“业务批次已删除但 reconciliation task 仍存在”的 task-only 行，使用 `fin_ops_platform.tools.cleanup_orphan_etc_reconciliation_tasks` 按显式 `--task-id` dry-run/execute 清理；工具必须走 service 删除边界，不直接 SQL 删除任务行。

## 变更记录

| 日期 | 变更 | 影响 | 验证 |
| --- | --- | --- | --- |
| 2026-08-13 | 点击创建草稿即进入暂存；creating/pending 均展示两个既有人工决定，App 不检测 OA 草稿；附件改为有界并发上传 | ETC bucket、manual-status 状态机、紧凑既有 HeroUI 操作区与 OA adapter；不新增状态、API、worker、read model 或数据库结构 | `tests/test_etc_backend.py`；`tests/test_audit_etc_tickets_read_model_tool.py`；`web/src/test/EtcTicketManagementPage.test.tsx`；`web/e2e/etc-tickets-flow.spec.ts` |
| 2026-08-03 | 已提交批次附件恢复支持对严格限定的历史 `canonical_invoice` 后补成员建立可信 PDF/XML 事实并纠正 ETC 元数据；保留已有 hash 的严格校验 | ETC 附件恢复 service、单页 PDF 校验复用、提交批次汇总和审计；不改成员/OA/relation/状态/read model/worker | `tests/test_etc_invoice_pdf_bundle_service.py` 68 张/4 张 bootstrap、身份拒绝、回滚、幂等与 68 页下载 |
| 2026-08-01 | ETC 页面改为左侧批次 rail + 右侧连续工作面，删除车牌/关键词页面查询链路，并新增基于既有 batch/task 状态的四阶段只读进度 | 仅 ETC 前端页面结构、展示投影与页面请求参数；后端 API/状态机/read model/worker/权限/跨页 I/O 不变 | `web/src/test/EtcTicketManagementPage.test.tsx`；`web/src/test/EtcApi.test.ts`；`web/e2e/etc-tickets-flow.spec.ts`；production build |
| 2026-07-19 | 固定 OA 草稿金额来自对账任务，业务批次发票汇总恢复为实际发票事实；结果弹窗收敛为两个明确决定并删除旧 batch DTO/伪金额映射 | ETC 页面与 business batch payload；无共享 read model/worker/跨页面 I/O 变化 | `tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_oa_draft_uploads_supplements_and_uses_oa_total`；`tests.test_audit_etc_tickets_read_model_tool`；`web/src/test/EtcTicketManagementPage.test.tsx`；`web/e2e/etc-tickets-flow.spec.ts` |
| 2026-07-14 | OA 草稿成功后新增批次 ETC 发票 PDF 合并下载；成员按 business batch 事实、单票单页、全有或全无，并写下载审计 | ETC 页面审批确认区、business batch read API、对象存储读取端口、PyMuPDF 合并边界 | `tests/test_etc_invoice_pdf_bundle_service.py`；`web/src/test/EtcApi.test.ts`；`web/src/test/EtcTicketManagementPage.test.tsx`；`web/e2e/etc-tickets-flow.spec.ts` |
| 2026-07-14 | 修复慢 OCR 与 source file 删除并发造成的孤儿解析结果；新增解析提交存在性校验、互斥、孤儿清理和 formal file row deleted 对账 | 信用卡/票根上传、source file 删除、对账任务 payload、PostgreSQL formal file 状态、409 错误合同 | `tests/test_etc_reconciliation_service.py`；`tests/test_etc_backend.py`；`tests/test_postgres_repositories_boundaries.py` |
| 2026-07-05 | 删除 ETC invoice-id 级 `/api/etc/invoices/revoke-submitted` 回退入口、旧 `/api/etc/batches*` 前端测试 mock 假后端和 ETC `oa-status/refresh` mock | ETC invoice list route owner 变为只读 I/O；提交状态回退只允许走 business batch 状态机；测试 mock 不再支持线上已删除旧入口 | `tests.test_platform_runtime_boundary_guards`；`tests.test_etc_backend.EtcServiceTests.test_batch_status_mark_not_submitted_and_draft_creation_with_fake_oa_client`；`web/src/test/EtcApi.test.ts` |
| 2026-07-01 | ETC 页面移除月份选择器，未提交业务批次支持提交前内联编辑标题并同步 linked task title | ETC 页面 UI 状态、business batch `title` payload、ETC 发票导入 ready task 下拉标题 | `tests.test_etc_backend.EtcServiceTests.test_business_batch_title_update_persists_and_locks_submitted`；`tests.test_etc_backend.EtcApiTests.test_business_batch_title_patch_updates_linked_task_title`；`web/src/test/EtcTicketManagementPage.test.tsx`；`web/src/test/EtcApi.test.ts` |
| 2026-06-17 | 补充 ETC 票据管理 Browser e2e，覆盖未提交业务批次、发票明细、OA 草稿创建、人工已提交确认和已提交 bucket 展示 | ETC 页面 UI 状态、business batch `imported -> oa_confirmation_pending -> manually_marked_submitted` 可见链路、Playwright smoke | `cd web && npx playwright test e2e/etc-tickets-flow.spec.ts` |
| 2026-06-12 | 删除 ETC repair/link/migration service 的 direct pair relation 写 fallback，缺少 Workbench relation command service 时 fail fast 且不先写本地批次 | 历史 repair、historical business batch migration、existing batch link、Workbench relation command 边界 | `tests/test_etc_backend.py`；`tests/test_historical_etc_business_batch_migration_service.py`；`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-12 | 已提交 ETC 业务批次删除/reset 在本地 mutation 前先校验 Workbench relation read model fresh，summary relation 取消、历史 repair 和 existing link 生产写入迁入 `WorkbenchRelationCommandService` | ETC 业务批次删除、绑定 reconciliation task 删除、历史 repair/migration/link 工具、Workbench relation 事实源 | `tests/test_etc_backend.py`；`tests/test_workbench_relation_command_service.py`；`tests/test_historical_etc_business_batch_migration_service.py`；`tests/test_platform_runtime_boundary_guards.py` |
| 2026-06-11 | 新建批次改为 `POST /api/etc/business-batches` 后端闭环创建 task + business batch，前端批次列表收敛到 business batch 事实源，task-only orphan 不再混入左侧列表 | `EtcBusinessBatchApplicationService`、ETC 页面、前端 API mapper/mock、API 契约、生产 orphan task 清理口径 | `tests.test_etc_backend`；`web/src/test/EtcTicketManagementPage.test.tsx`；`web/src/test/EtcApi.test.ts`；ETC cleanup tool tests |
| 2026-06-10 | 将 ETC reconciliation task 删除改为持久 deleted tombstone，并新增显式 allowlist 的 orphan task 清理工具，防止部署/重启后 task-only 批次复活 | `EtcReconciliationTaskService`、Postgres ETC repository、业务批次删除 API、生产维护工具 | `tests.test_etc_reconciliation_service`；`tests.test_etc_backend`；`tests.test_postgres_repositories_boundaries`；`tests.test_cleanup_orphan_etc_reconciliation_tasks_tool` |
| 2026-06-11 | 首轮测试闭环文档化，补充模块影响面、smoke flows 和主控依赖图 | ETC 页面、business batch、reconciliation task、import worker、Workbench summary、App Status | `tests.test_etc_backend`；`tests.test_etc_reconciliation_service`；`tests.test_import_service`；`tests.test_workbench_sql_runtime`；`web/src/test/EtcTicketManagementPage.test.tsx`；`web/src/test/EtcApi.test.ts`；`bash scripts/verify.sh docs` |
| 2026-06-10 | 修复 ETC 导入/OA 草稿后本地 canonical invoice 持久化弱 fingerprint 冲突，并补齐导入失败 job 的同 session 重试语义，清理旧 ETC OA detection 部署残留 | ImportNormalizationService、Postgres invoice repository、runtime import worker、BackgroundJobService、ETC import confirm API、migration、RabbitMQ 部署样例 | `tests.test_import_service`；`tests.test_postgres_core_repository`；`tests.test_platform_runtime_boundary_guards`；`tests.test_postgres_migrations`；`tests.test_rabbitmq_staging_preflight`；`tests.test_etc_backend` |
| 2026-06-10 | 清理 ETC 任务删除旧状态阻塞，并确认页面初始化不自动创建空任务 | reconciliation task 删除、旧 batch 删除兼容入口、ETC 页面初始化请求 | `tests.test_etc_backend`；`tests.test_etc_reconciliation_service`；`web/src/test/EtcTicketManagementPage.test.tsx` |
| 2026-06-09 | 彻底移除 ETC 专用 OA 自动检测后端链路，草稿后统一进入 `oa_confirmation_pending` 等待人工确认 | ETC business batch API、worker registry、OA projection/Mongo adapter、前端状态显示、历史状态迁移 | `tests.test_etc_backend`；`tests.test_platform_runtime_boundary_guards`；`tests.test_oa_projection_sql_runtime`；`tests.test_mongo_oa_adapter`；`web/src/test/EtcTicketManagementPage.test.tsx`；`web/src/test/EtcApi.test.ts` |
| 2026-06-09 | ETC 批次删除入口统一为任意阶段本地清理；绑定 summary 的 active relation 取消且不恢复历史 OA+流水二栏关系 | ETC 任务入口删除、业务批次入口删除、Workbench active relation、summary 释放和已存在 canonical invoice 可见性恢复 | `tests.test_etc_backend`；`tests.test_workbench_pair_relation_service`；`web/src/test/EtcTicketManagementPage.test.tsx` |
| 2026-06-09 | 已提交 ETC 业务批次支持本地删除/重置，释放合并关系但保留 OA 和已闭环任务事实 | ETC 页面 submitted bucket、业务批次状态、summary 释放和已存在 canonical invoice 可见性恢复 | `tests.test_etc_backend`；`web/src/test/EtcTicketManagementPage.test.tsx` |
| 2026-06-09 | `etc_invoice_summary` 增加结构化金额并写入 workbench numeric/search 字段，同时修复历史已提交批次数据 | 关联台金额搜索、ETC 历史批次闭环、Workbench read model | `tests.test_workbench_sql_runtime`；生产数据 SQL 验证 |
| 2026-06-09 | Workbench SQL projection 将已提交 ETC 业务批次作为 `etc_invoice_summary` 一等来源，repository 持久化业务批次上报金额和数量 | ETC 人工已提交批次、关联台 open 区 summary、Postgres read model | `tests.test_workbench_sql_runtime`；`tests.test_etc_backend`；`web/src/test/EtcTicketManagementPage.test.tsx` |
| 2026-06-08 | ETC 页面统一为单个业务批次链路；人工确认已提交后闭环对账任务并投影 `etc_invoice_summary` | ETC 批次、关联台 open 区、人工确认 API | `tests.test_etc_backend`；`web/src/test/EtcTicketManagementPage.test.tsx` |
