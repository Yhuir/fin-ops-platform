# ETC票据管理 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/EtcTicketManagementPage.tsx`、`web/src/features/etc/EtcBatchProgress.tsx` | unsubmitted/staged/submitted 三 bucket、HeroUI 原生等宽全宽状态切换、50 条服务端分页、`total > 100` 全页可达、bucket/page 请求身份与末页回退、无本地跨 bucket 数组/计数伪更新、无月份/车牌/关键词页面搜索链路、左侧批次 rail + 右侧连续工作面、四阶段状态投影、完成阶段只保留标题、summary 首屏、单次精确 detail、同一选中行重复点击不清空明细且不追加 detail 请求、无 full task list/双 selection、禁用态不展示冗余原因、OA intent idempotency、OA 提交金额与实际发票金额分离展示且仅在不一致时显示紧凑差额及既有差额原因、两按钮暂存确认/退回未提交、error/loading/delete dialog、暂存与已提交发票明细标题栏复用批次 PDF 下载且不触发折叠、source file 和严格浏览器错误捕获 |
| Frontend API mapper | `web/src/features/etc/api.ts` | `/api/etc/business-batches*` 三 bucket/count/action envelope、精确 detail、OA create 长请求与 manual-status contract、发票 PDF blob/UTF-8 文件名、HTML/proxy error、multipart upload、stale preview error、本地化错误、旧 `/api/etc/batches*` 和 `/api/etc/invoices/revoke-submitted` API 不得回归 |
| Workbench UI | `web/src/components/workbench/CandidateGroupGrid.tsx` | `etc_invoice_summary` 折叠/展开、open/paired 区显示、撤回/删除后 summary 释放和已存在 canonical invoice 可见性 |
| HTTP routes | `server.py` `/api/etc*` | business batch、business batch title patch、reconciliation task、只读 invoice list、`invoice-pdf` 二进制响应/错误码/权限、submitted 批次附件受限恢复的 admin/version/hash/idempotency 合同、import preview/confirm、source files、manual status、delete/reset 的状态码和结构化错误；慢解析期间 source file 被删除时必须返回 409 / `source_file_deleted_during_parse`；旧 `/api/etc/batches*`、`/api/etc/business-batches/{id}/oa-status/refresh`、`/api/etc/invoices/revoke-submitted` 不得回归 |
| Business service | `EtcService`、`EtcBatchInvoiceLinkService` | 业务批次幂等、标题持久化/版本/提交后锁定、状态流转、OA 附件有界并发与稳定顺序、finalize 失败 outcome-unknown、ETC metadata/附件占用释放、已存在 canonical invoice 关联、ETC batch invoice link 幂等写入、历史 batch 迁移、删除 audit |
| Application service | `EtcBusinessBatchApplicationService`、`EtcInvoicePdfBundleService` | OA 草稿、creating/pending manual OA status、管理员历史 recovery、source file、绑定 task 恢复、发票 PDF actor scope/草稿或 submitted 资格/历史无草稿批次/成员/排序/单页/大小/hash/审计、OA 上传 absolute URL 归一与未知 host fail-closed、Workbench invalidation |
| Reconciliation service | `EtcReconciliationTaskService`、`CcbCreditCardStatementParser` | task ready/importing/imported/closed/deleted、source files、version、tombstone、重启 hydrate；统一不可信文件边界拒绝伪装后缀、未知二进制与超限资源且不落对象存储；信用卡 PDF 可选文字优先、图像型 PDF 逐页布局 OCR fallback、OCR 人工核对 warning；解析提交与删除互斥、已删除来源拒绝提交、历史孤儿解析结果可审计清理 |
| Import worker | `ImportProcessingService`、runtime import worker | `etc_invoice_import` job、同 session 重试/幂等、后台导入成功后的 business batch 与 ETC metadata/附件关系保存，以及常驻 API 无需重启即可读取 worker 的 PostgreSQL 写入 |
| Workbench direct query | `PostgresWorkbenchPageQueryRepository`、`WorkbenchPairRelationService` | normal GET 从 canonical submitted business batch 构造 `etc_invoice_summary`、active relation 排除 open summary、submitted ETC 重叠正式发票不再作为普通 open invoice row、delete/reset 后不恢复旧 OA+银行二栏 relation；零 page projection/cache/queue |
| 运维工具 | cleanup/migration/repair tools | orphan task 清理必须显式 allowlist；历史迁移 dry-run/execute 不能绕过 service 边界；submitted ETC overlap 与缺失成员修复必须 dry-run-first、fingerprint-bound、幂等且 execute 需要 reason/operator |
| App Status | import worker、`workbench_relation`/matching、App Health | import job、shared relation/matching runtime、ETC route/API smoke、Nginx HTML/502 风险；不登记 Workbench page read model |

## 关键 smoke flows

- 可选文字或图像型信用卡 PDF 上传 -> 文本解析或布局 OCR -> 票根文件上传 -> reconciliation task ready -> ETC ZIP preview -> confirm import job -> business batch visible -> OA draft -> manual submitted -> Workbench open 区出现 `etc_invoice_summary`。
- OA 草稿已创建 -> read-export 用户点击“下载发票PDF” -> `invoice-pdf` 读取 business batch 的 68 个 PDF -> 输出一份 68 页文件 -> 浏览器使用服务端 UTF-8 文件名保存；任一来源异常时不下载部分文件。
- 历史 submitted 批次附件对象缺失 -> 管理员上传原始 ZIP + expectedVersion + reason -> 已有 hash 严格相等；严格限定的 `canonical_invoice` 后补成员经强身份/PDF/成员校验后建立 PDF/XML 并纠正 ETC 元数据 -> 再次执行零写入 -> 68 张合并 PDF 恢复为 68 页；普通用户、hash/身份不同、成员不一致或持久化失败必须不留下半写事实。
- Browser e2e：ETC 票据管理首屏 business-batches 暂时 503 -> 错误态且无普通空态 -> 点击刷新恢复未提交业务批次和发票明细；未提交/已提交删除、source file 删除和 ticket-root 上传的首次暂时失败都保持可重试；创建 OA 草稿前显示 OA 金额、实际发票金额和非阻断差额，点击后立即进入暂存并显示两个决定，请求中按钮禁用、请求完成后可用；后端返回 creating 的重载页面仍在暂存且无需 recovery UI；人工确认暂时失败保持可重试，成功后进入目标 bucket。所有成功路径检查无可见错误残留。
- 用户点击“新建批次” -> `POST /api/etc/business-batches` 可省略 `taskId` -> 后端创建 task + active business batch -> 未提交列表只显示返回的 business batch；若 business batch 创建失败，新建 task 必须 tombstone，不得留下刷新后复活的 task-only 批次。
- 用户在未提交列表点击批次标题 -> 内联编辑 -> `PATCH /api/etc/business-batches/{id}` 持久化 `title` 并同步 linked reconciliation task title -> ETC 发票导入页 ready task 下拉显示新标题；已提交批次标题不可编辑。
- business batch manual `not_submitted` -> 释放 ETC 发票占用 -> 回到未提交链路，不触发自动检测。
- 任意阶段 business batch delete/reset -> 删除本地导入和 task/source metadata -> 已提交 summary 消失；只有原本已存在于统一发票池的发票才可能回到普通发票视图。若 summary 已 active relation，取消 relation 且不恢复旧二栏关系。
- source file/object storage failure -> API 返回稳定 storage error -> 不留下半写入 source file、版本号或审计。
- source file 已落库 -> 慢 OCR 未完成时并发删除 -> 删除成功 -> OCR 提交返回 409 -> task 不包含孤儿 parse result/card item；历史孤儿按同一 `file_id` 删除后 formal file row 标记 `deleted`。
- failed/acknowledged/cancelled ETC import job -> 同 session 可重新 confirm；queued/running/recent succeeded 才允许幂等复用。
- 历史 ETC batch migration dry-run -> execute -> submitted bucket 可见 -> Workbench paired/open 口径一致。
- Nginx/API smoke -> `/api/etc/business-batches*` 必须返回 JSON，不得返回 HTML、502 或 React shell。
- 121 个业务批次 -> 页面按 `page_size=50` 请求第 1/2/3 页 -> 第 51、101、121 条可见，rail 总数保持 121，旧页条目不会与新页拼接。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_import_service.py` | 覆盖信用卡 PDF 文本/OCR、business batch 标题/版本/状态、creating 与 pending 的人工决定、creating 暂存 bucket、幂等草稿 attempt、历史管理员 recovery、已提交批次、金额、ETC metadata、canonical invoice owner 保留、删除/reset 和非法输入。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_import_service.py`、`tests/test_etc_batch_invoice_link_service.py`、`tests/test_postgres_core_repository.py`、`tests/test_postgres_state_store_integration.py`、`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_query_postgres_integration.py`、`tests/test_workbench_pair_relation_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py`、`tests/test_repair_submitted_etc_invoice_overlaps_tool.py`、`tests/test_repair_submitted_etc_batch_members_tool.py`、`tests/test_backfill_etc_batch_invoice_links_tool.py` | 覆盖 ETC business batch service 调用对账任务闭环、`EtcBusinessBatchApplicationService.create_batch_payload` 在省略 `taskId` 时创建 task + business batch 且创建失败会 tombstone 新 task、0101 形态历史任务经 0103 backfill 后与当前任务共同 hydrate/list/ready-list 的真实 PostgreSQL 回归、durable import job 活跃时对账任务不被启动恢复打断、runtime worker 从 `EtcImportResult.items` 回查 ETC metadata 且不创建 canonical invoice、北京速通信用卡项进入 ETC 候选并与同日同金额票根网 TXT 自动配对、无同窗口票根的信用卡项会按剩余同金额票根选择最近日期推荐配对、对账任务多候选时最大化一对一配对并按最近日期优先自动链接、业务批次已成功导入但 task 停在 ready 时创建 OA 草稿前的一致性补偿、ETC batch invoice link 幂等 upsert、历史 link backfill dry-run/apply/rollback 边界、repository 只按 business batch 实际 `invoice_ids` 成员落库发票数量/含税金额并覆盖 OA 报送金额污染、审计、已提交批次 reset 链路、importing/closed/submission link 等任意阶段任务删除、删除后的 reconciliation task 以 `deleted` tombstone 防止部署重启复活、summary active relation 通过 Workbench relation command service 取消且不恢复旧 OA+流水二栏关系、历史 repair 通过 command service 写 relation；submitted batch 与 completed OA 的正式关系归属由 deterministic matching UoW 自动补全、submitted ETC overlap repair 和缺失成员 repair 的 dry-run/fingerprint/partial-state/idempotent边界、ETC OA 检测 worker/adapter 不再注册、旧 `EtcBusinessBatch` pickle 中已移除的 `oa_detection_status` 字段会被安全丢弃并补齐当前默认字段，以及对象存储失败时对账任务上传状态不留下半写入 source file。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖信用卡 PDF multipart 上传返回 source file、已解析 ETC 候选项和稳定 `parseIssues` 合同；`POST /api/etc/business-batches` 省略 `taskId` 时返回已绑定 task 和 title 的 business batch 且重启后 active business batch 持久可见、`PATCH /api/etc/business-batches/{id}` 更新 title并同步 linked task title、空标题和提交后锁定错误码、`manual-oa-status` 后响应、submitted bucket、兼容 `month` 筛选优先使用业务批次归属月份，缺失归属月份时按开票/通行日期匹配，且 counts 与 items 使用同一筛选口径、Workbench row shape、`DELETE /api/etc/business-batches/{id}` 对已提交批次返回本地 reset 结果、relation distribution stale 时仍通过 canonical relation command 删除 batch 并取消 summary relation、`DELETE /api/etc/reconciliation-tasks/{id}` 通过绑定业务批次执行同一删除链路、旧 task-only submission/import metadata 链路也不再返回 submitted confirmation guard、业务批次删除后重启不会重新出现在 `/api/etc/reconciliation-tasks`、ETC 导入确认失败 job 不阻塞同 session 重试、ETC `oa-status/refresh` 已移除且 business batch payload 不再输出 `oaDetection*` 字段、`/api/etc/invoices` route owner 只保留只读列表 I/O、`/api/etc/invoices/revoke-submitted` 已删除且 `EtcService` 不保留 invoice-id 级回退方法、ETC 票根网 TXT 上传支持 UTF-8/GB18030/GBK 文本并走 clipboard parser，以及 ETC 源文件上传在对象存储不可写时返回 `reconciliation_file_storage_unavailable`/503。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_workbench_query_postgres_integration.py`、`tests/test_workbench_relation_command_service.py`、`tests/test_postgres_repositories_boundaries.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_background_job_service.py` | 覆盖 Workbench direct query 从业务批次表构造 open `etc_invoice_summary`、匹配 OA 时追加汇总行、active relation 已存在时 open 区过滤陈旧 ETC summary、已提交批次 reset 后 summary 消失、包含 summary 的 active relation 取消后 OA/银行流水不恢复二栏配对，且页面 GET 零 projection/cache/queue；delete/reset 使用 canonical relation 写安全且不被 `workbench_relation` distribution non-fresh 阻断，durable ETC import job 活跃 session 阻止 task hydration recovery，failed/acknowledged/cancelled 导入 job 不被同 session 幂等复用，deleted reconciliation task 重启后不 rehydrate 且 Postgres formal file rows 被清理，runtime import worker 与 API import confirm 使用同一 ETC metadata/已存在 canonical invoice 关联口径，后台 job helper 等待 runner 完成后再释放测试数据目录，`tests/test_etc_backend.py` 已清零 `TemporaryDirectory(ignore_cleanup_errors=True)` 并用 API/service/import/Workbench 组合回归验证严格 cleanup，并验证展示金额与结构化 `amount_value`/numeric 金额列同时存在以支持金额搜索。 |
| 4a. Page Audit direct-canonical proof | 适用 | `tests/test_audit_etc_tickets_read_model_tool.py`、`tests/test_page_audit_registry.py`、`tests/test_app_health_api.py`、`web/src/test/PageAuditIcon.test.tsx` | 覆盖零 page read model、统一 API dispatch、三 bucket、creating durable attempt 且不做 OA 外部超时判断、pending draft/submission、submitted/not-submitted occupancy、typed edges、canonical invoice bridge、import queue、只读 snapshot 和 UI direct-canonical success gate。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/e2e/etc-tickets-flow.spec.ts`、`docs/modules/etc-tickets/e2e-spec.md`、`docs/modules/etc-tickets/e2e-coverage.md` | 覆盖单一批次列表、未提交/暂存/已提交三个 tab 采用 HeroUI `fullWidth` 且 Chromium 实测三项等宽、页面不展示内部 task version/完成阶段说明/来源说明/相等说明/禁用原因、页面无月份/车牌/关键词搜索框且列表请求只发送 bucket/page/page_size、左侧 rail/连续工作面/扁平分隔 CSS 合同、四阶段在 draft/reviewing/ready/importing/imported/OA pending/failed/submitted 下的语义映射与窄屏当前阶段、未提交批次标题内联编辑并刷新 linked task title、business-batches 首屏暂时失败错误态、防普通空态和刷新恢复、页面初始化不读取 full task list、orphan reconciliation task 不进入业务批次列表、“新建批次”调用 `createEtcBusinessBatch({})` 而不是前端创建空 task、workflow 只按绑定 task 精确读取、3740.82 对账任务 OA 金额与 3686.36 实际发票金额分离展示及 54.46 非阻断差额、结果弹窗只保留两个明确决定、草稿成功后即使 selection 迁移仍保留完整 batch/version 与 OA 金额快照作为确认 target、确认后进入已提交或退回未提交、无自动检测入口、草稿创建失败 dialog 保持、OA draft 暂时失败可重试且不进入提交确认伪成功、manual OA status 暂时失败可重试且不切已提交 bucket、未提交 business batch delete 暂时失败可重试且不移除行/不关闭弹窗、已提交 business batch reset/delete 暂时失败可重试且不移除已提交行/不改变计数/不关闭弹窗、source file delete 暂时失败可重试且不移除文件/不关闭弹窗、ticket-root source upload 暂时失败可重试且不追加文件/成功后清除错误、前端 API/mock 不再暴露旧 `/api/etc/batches*`、`/api/etc/invoices/revoke-submitted` 或 ETC `oa-status/refresh`、任意阶段删除入口不因 OA/导入状态禁用、已提交批次删除确认文案、local reset 调用、ETC summary 展开明细按钮、大 ZIP 预览上传不会被普通 API timeout 提前截断，以及真实 Chromium 中三 bucket、四阶段、PDF 下载、失败恢复、未提交 -> OA 草稿暂存 -> 人工已提交、严格浏览器错误捕获和成功后无可见错误残留的可见闭环；新增 121 条 fixture，证明 `page_size=50`、第 2/3 页、第 121 条、服务端 total 与旧页替换；状态写后列表由服务端当前/目标 bucket 页重读，不使用本地 prepend/filter/count 算术。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py`、`web/e2e/etc-tickets-flow.spec.ts` | 覆盖导入/批次/人工提交/创建 OA 草稿/对账任务闭环/关联台展示/已提交批次本地 reset、任务入口删除绑定业务批次并取消 summary relation 的关键路径，并覆盖 durable import restart 后业务批次与 linked task 的一致性恢复；Playwright 补充真实浏览器 business-batches GET 暂时失败 -> 刷新 -> 恢复批次/明细、未提交 business batch delete 暂时失败 -> 弹窗/行保持 -> 重试成功后列表刷新、已提交 business batch reset/delete 暂时失败 -> submitted row/计数保持 -> 重试成功后列表刷新、source file delete 暂时失败 -> 弹窗/文件行保持 -> 重试成功后文件列表刷新、ticket-root source upload 暂时失败 -> 不追加文件 -> 重试成功后追加 source file、OA draft 暂时失败 -> dialog 保持 -> 重试成功、manual OA status 暂时失败 -> 保持提交确认 -> 重试成功，以及从未提交业务批次创建 OA 草稿到人工已提交 bucket 的页面闭环和成功后错误残留检查；Playwright 额外覆盖 121 批真实浏览器翻页和请求参数，防止统计完整但 100 条后的业务批次不可达。 |
| 7. Existing feature regression tests | 适用 | `tests/test_etc_backend.py`、`tests/test_object_storage_repository.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_postgres_migrations.py`、`tests/test_postgres_state_store_integration.py`、`tests/test_rabbitmq_staging_preflight.py`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/e2e/etc-tickets-flow.spec.ts` | 覆盖既有 ETC 页面旧入口、OA 匹配汇总行、删除/文件/补充凭证交互、OA projection/Mongo adapter 删除 ETC 专用候选查询后不影响非 ETC OA 能力、对象存储 repository 暴露 backend/bucket 给 PostgreSQL 文件写入，migration 清单连续且 0103 只从 typed 时间列幂等补齐缺失 payload 时间，RabbitMQ staging preflight 不再要求 ETC OA detection worker，防止首屏加载失败被伪装为空态、历史任务与新任务混排导致 list/ready-list 500、未提交/已提交 business batch delete/reset 暂时失败被伪装成已删除、source file delete 暂时失败被伪装成已删除、ticket-root source upload 暂时失败被伪装成已上传、OA draft 暂时失败被伪装成提交确认成功、manual OA status 暂时失败被伪装成已提交、旧撤销提交入口、旧检测入口、旧删除状态阻塞、浏览器层 OA 草稿确认流程和“成功但报错提示仍显示”重新漂移。 |

## 2026-07-22 页面统计快照回归

- `tests/test_etc_backend.py::EtcApiTests::test_etc_business_batch_summaries_use_one_repeatable_read_only_snapshot` 证明 bucket 计数、完整性统计和当前分页 items 的两条有界 SQL 只在同一个 `REPEATABLE READ READ ONLY` 快照连接上执行。

## 2026-07-14 import worker 跨进程查询可见性增量

- 类别 2（service）：`tests/test_etc_backend.py::EtcApiTests::test_etc_query_services_reload_worker_writes_from_postgres_state_store` 先构造 API query services，再由独立 worker services 写入共享 PostgreSQL 语义 store，断言 task、business batch 和 invoice 无需重启即可读取。
- 类别 3（API 合同）：response shape 未变；既有 ETC API 套件继续保护 task、business batch 和 invoice payload。
- 类别 4（background job/state）：适用。回归保护 worker 成功落库后页面不再停留在启动时快照；file/memory backend 不启用 reload，现有本地状态测试继续保护原行为。
- 类别 5（前端）不新增测试：页面调用及 DTO 未变，根因在 PostgreSQL service 查询一致性；既有组件与 Chromium 导入 flow 已覆盖刷新后的用户可见行为。
- 类别 6/7（端到端与回归）：真实 68 条生产任务用于 PostgreSQL + MinIO worker drain 与部署后 API 只读 smoke；后端完整 ETC 套件保护既有导入、对账、OA 与删除链路。

## 2026-07-18 OA attempt 并发与页面 selection 回归增量

- 类别 1（业务核心）：严格校验 recovery decision 是唯一 JSON boolean，已创建与未创建证据互斥；缺 linked reconciliation task 时 list/detail action 与 command 一律 fail closed。
- 类别 2/4（service、持久化）：覆盖目标 business batch version lock/CAS、两个独立 service/store 实例下 finalize 不覆盖其它批次更新、linked task 元数据第一次持久化失败后同 key 重放不创建第二个 OA，以及 recovery adoption 的同证据修复重放；补充真实 `EtcReconciliationTaskService + ApplicationStateStore` 保存失败回滚，验证同实例恢复原 metadata/version/audit counter，重试后跨实例只有一次 durable `oa_draft_created`。
- 类别 3（API）：覆盖非法 boolean/互斥 recovery payload 返回 422，合法 OA command 必须有 imported/closed linked task。
- 类别 5（前端）：`EtcTicketManagementPage.test.tsx` 覆盖 detail/task 并发、切换批次立即失效旧 mutation target、异步刷新列表自动选择新批次时同步失效旧 task 且旧 task mutation 请求为零、显式暂存行优先于旧 draft result，以及 manual status 成功后目标 bucket list 只发起一次 GET。
- 类别 6（端到端）：真实 OA 和独立生产进程竞争仍留给部署后受控 smoke；本地 service/API 组合已覆盖不重复创建和 durable convergence。
- 类别 7（回归）：ETC backend 全量与 71 项页面交互回归保护导入、OA、撤回、删除和列表既有行为；Audit 额外覆盖正式 row `updated_at` 被无关 upsert 刷新时仍以 durable attempt event/payload 时间判 stale，以及 not-submitted 历史成员被另一个已提交批次合法复用、发票状态已为 submitted 时整页 Audit 仍通过。

## 2026-07-14 发票 PDF 合并下载回归增量

- 类别 1（业务核心）：适用。`tests/test_etc_invoice_pdf_bundle_service.py` 以真实 PDF 字节覆盖 68 张=68 页、稳定顺序、空批次/无草稿、缺失/损坏/hash 不一致/多页和资源上限。
- 类别 2（service）：适用。同一测试覆盖 application service 的 actor scope、批次成员解析、文件读取端口、全有或全无和下载审计；不直接依赖 MinIO client 或 HTTP response。
- 类别 3（API 合同）：适用。覆盖成功二进制 response、UTF-8 文件名、no-store、数量/页数 headers、无草稿 409 和结构化错误映射；业务路由不写 `Content-Length`，由统一 HTTP handler 只发送一次，防止 Nginx 因重复长度头返回 502。
- 类别 4（read model/cache/job）：不适用。下载只读 canonical business batch + 对象存储字节，不新增或刷新 read model，不入队 worker，不写缓存/预生成文件。
- 类别 5（前端交互）：适用。Vitest 覆盖 blob、文件名、结构化错误、按钮点击和 URL 释放；Playwright 覆盖 read-export 用户可见按钮、浏览器 download event 和服务端文件名。
- 类别 6（端到端）：适用。本地 API + 浏览器组合覆盖 OA 草稿存在 -> 合并 API -> 浏览器下载；生产 PostgreSQL + MinIO 真实对象属于发布后只读 smoke。
- 类别 7（既有功能回归）：适用。复跑 ETC API/页面既有套件，保护 OA 人工确认、删除/reset、导入、页面按钮和代理 fallback 不受影响。

## 2026-08-03 历史后补成员附件恢复回归增量

- 类别 1（业务核心）：适用。真实目标发票号/金额组合覆盖 exact `canonical_invoice` bootstrap、发票身份不一致拒绝、已有 hash 严格分支和幂等版本。
- 类别 2（service）：适用。覆盖嵌套 ZIP、对象写入、原始 XML 元数据、提交批次汇总、逐发票审计，以及持久化失败后的 preimage 与对象删除。
- 类别 3（API 合同）：适用。管理员 multipart 恢复返回 `sourceBootstrapped/metadataRepaired`，随后下载响应为 68 张/68 页；既有普通用户 403 合同继续保留。
- 类别 4（read model/cache/job）：不适用。恢复只写 ETC canonical batch/invoice 附件事实，不新增 read model、缓存、队列或 worker。
- 类别 5（前端交互）：不适用。页面和前端 API 没有变更；该入口为管理员受控运维 API，用户下载按钮复用既有合同。
- 类别 6（端到端）：适用。本地组合覆盖 64 张完整 + 4 张后补 -> 原始嵌套 ZIP 恢复 -> 68 页合并下载 -> 幂等重放；生产使用用户提供原始 ZIP 做同一受控闭环。
- 类别 7（既有功能回归）：适用。已有 hash 恢复、hash mismatch、缺失/损坏/多页 PDF 和普通下载行为继续由同一测试文件保护，并复跑 ETC service/API/边界套件。

## 2026-07-14 慢解析并发删除回归增量

- 类别 1（业务核心）与类别 2（service）：`tests/test_etc_reconciliation_service.py` 覆盖已删除来源拒绝解析提交、孤儿 parse/card 数据清理和审计事件。
- 类别 3（API 合同）：`tests/test_etc_backend.py` 覆盖信用卡 multipart 上传在解析提交前被删除时返回 409 / `source_file_deleted_during_parse`，以及既有 DELETE source API 清理历史孤儿。
- 类别 4（持久化/read model）：`tests/test_postgres_repositories_boundaries.py` 覆盖 active task 保存时仅把 snapshot 缺失的 formal file rows 标记 `deleted`，保留当前 source file id。
- 类别 7（既有功能回归）：上述 API 用例同时断言 source、parse result、card item 三者不会再次分裂；既有正常信用卡 PDF/OCR 上传测试继续保护成功路径。
- 类别 5（前端交互）不适用：前端 mapper 和渲染没有改动，页面原本就完整展示 API `sourceFiles`；根因与修复均在后端并发提交边界。
- 类别 6（端到端）本地以 API 组合测试覆盖上传/删除/提交竞争；真实生产修复按版本先清理孤儿再重传 PDF，结果纳入发布 smoke。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_invoice_pdf_bundle_service -v
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_workbench_matching_orchestrator.py tests/test_workbench_formal_relation_repository.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py::EtcApiTests::test_etc_summary_relation_cancel_delegates_to_workbench_relation_command_service tests/test_etc_backend.py::EtcApiTests::test_submitted_etc_business_batch_delete_uses_canonical_relation_when_read_model_is_stale -q
PYTHONPATH=backend/src python3 -m unittest tests.test_import_service tests.test_postgres_core_repository -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_rabbitmq_staging_preflight -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
FIN_OPS_TEST_DATABASE_URL=<disposable-postgres-url> PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_state_store_integration.py::PostgresStateStoreIntegrationTests::test_timestamp_repair_restores_mixed_historical_and_current_task_lists -q
PYTHONPATH=backend/src python3 -m unittest tests.test_object_storage_repository tests.test_file_object_storage tests.test_etc_reconciliation_service -v
PYTHONPATH=backend/src python -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_matching_links_beijing_sutong_card_rows_to_ticket_root_txt_rows -q
PYTHONPATH=backend/src python3 -m unittest tests.test_background_job_service -v
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_batch_invoice_link_service.py tests/test_postgres_repositories_core.py::test_upsert_etc_batch_invoice_link_is_idempotent_by_batch_identity tests/test_postgres_migrations.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_repair_submitted_etc_invoice_overlaps_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_backfill_etc_batch_invoice_links_tool.py tests/test_workbench_query_postgres_integration.py::WorkbenchQueryPostgresIntegrationTests::test_page_etc_hydration_is_one_statement_and_matches_legacy_dto -q
PYTHONPATH=backend/src python3 -m pytest tests/test_restore_deleted_etc_business_batch_tool.py tests/test_backfill_etc_batch_invoice_links_tool.py tests/test_etc_backend.py -k 'linked_submitted_business_batch or deleted_submitted_business_batch or backfill' -q
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_closes_the_linked_reconciliation_task -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcServiceTests.test_business_batch_title_update_persists_and_locks_submitted tests.test_etc_backend.EtcApiTests.test_business_batch_title_patch_updates_linked_task_title -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_gb18030_txt_file_with_clipboard_parser -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_cascades_mutable_batch_contents tests.test_etc_backend.EtcApiTests.test_etc_business_batch_detail_returns_invoice_items_without_detection_fields tests.test_etc_backend.EtcApiTests.test_etc_business_batch_scope_uses_session_dept_id tests.test_etc_backend.EtcApiTests.test_etc_business_batch_oa_draft_waits_for_manual_confirmation_without_detection_runtime tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_files_append_to_reconciliation_task tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_etc_business_manual_status_accepts_confirmation_pending_state tests.test_etc_backend.EtcApiTests.test_etc_business_batch_submitted_list_counts_use_filtered_passage_month tests.test_etc_backend.EtcApiTests.test_historical_business_batch_lists_by_scope_month_and_reported_amount tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_creates_open_workbench_summary_with_reported_amount tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_releases_summary_and_deletes_local_task tests.test_etc_backend.EtcApiTests.test_legacy_submission_batch_delete_delegates_to_business_batch_reset tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_cancels_summary_relation_without_restoring_oa_bank_pair tests.test_etc_backend.EtcApiTests.test_etc_summary_relation_cancel_delegates_to_workbench_relation_command_service tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_uses_canonical_relation_when_read_model_is_stale tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_cancels_submitted_business_summary_relation tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_removes_orphan_submission_metadata_link tests.test_etc_backend.EtcApiTests.test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle tests.test_etc_backend.EtcApiTests.test_historical_etc_repair_requires_relation_command_service_before_local_writes -v
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_page_query_repository.py tests/test_workbench_query_postgres_integration.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_deleted_task_does_not_rehydrate_from_postgres_retained_row_or_reuse_id tests/test_etc_backend.py::EtcApiTests::test_deleted_business_batch_route_tombstones_task_after_postgres_rehydrate tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_deleted_reconciliation_task_clears_formal_file_rows tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_uploaded_parse_result_rejects_source_deleted_before_parse_commit tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_delete_source_file_cleans_existing_orphan_parse_result tests/test_etc_backend.py::EtcApiTests::test_credit_card_statement_upload_rejects_parse_commit_after_source_deleted tests/test_etc_backend.py::EtcApiTests::test_delete_reconciliation_source_file_route_cleans_orphan_parse_result tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_multi_table_saves_use_transactions -q
python -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_active_import_session_is_not_recovered_after_hydration tests/test_etc_backend.py::EtcApiTests::test_business_batch_oa_draft_recovers_linked_task_after_durable_import_restart
python -m pytest tests/test_etc_reconciliation_service.py tests/test_etc_backend.py tests/test_import_service.py -q

cd web && npm test -- --run src/test/EtcTicketManagementPage.test.tsx src/test/CandidateGroupGrid.test.tsx
cd web && npm test -- --run src/test/EtcApi.test.ts
cd web && npx playwright test e2e/etc-tickets-flow.spec.ts
cd web && npm run e2e:smoke
cd web && npm run build
bash scripts/verify.sh docs
```

## Nightly CI 覆盖

夜间 CI 应包含：

- 后端 ETC/API/service/import/workbench direct query 组合：`tests.test_etc_backend`、`tests.test_etc_reconciliation_service`、`tests.test_import_service`、`tests/test_workbench_page_query_repository.py`、`tests/test_workbench_query_postgres_integration.py`、`tests.test_workbench_pair_relation_service`、`tests.test_platform_runtime_boundary_guards`、ETC cleanup/migration tool tests。
- 前端 ETC/API/Workbench summary 组合：`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/CandidateGroupGrid.test.tsx`。
- Playwright browser smoke：`web/e2e/etc-tickets-flow.spec.ts` 覆盖 business-batches 首屏暂时 503 -> 刷新恢复、未提交 business batch delete 暂时 503 -> 保持确认弹窗/批次行 -> 重试成功、已提交 business batch reset/delete 暂时 503 -> 保持确认弹窗/已提交批次行/计数 -> 重试成功、source file delete 暂时 503 -> 保持确认弹窗/文件行 -> 重试成功、ticket-root source upload 暂时 503 -> 不追加文件 -> 重试成功、OA draft 暂时 503 -> 保持 dialog -> 重试成功、manual OA status 暂时 503 -> 保持提交确认 -> 重试成功，以及未提交业务批次 -> OA 草稿 -> 人工已提交 bucket，并检查成功后无可见错误残留。
- `bash scripts/verify.sh docs`。

## 未测风险

- `tests.test_etc_backend` 中依赖本机真实票据样例的用例在样例缺失时会 skip；核心 ETC 业务批次和 Workbench direct query 路径不依赖这些样例。
- ETC 票据管理已补 Spec-first E2E 合同和覆盖映射；本地 covered 不代表真实大 ZIP、对象存储、真实 OA、生产历史迁移或真实 worker drain 已完成。
- 真实大 ZIP、票根网 PDF/XML/TXT 混合包、Nginx 上传超时和对象存储权限仍需要 staging/生产前 smoke。
- 图像型信用卡 PDF 的 OCR 准确率依赖源文件分辨率、旋转和表格密度；自动测试已证明 fallback 与行结构，但真实扫描件仍必须根据 warning 核对行数、日期和金额。
- 真实 OA 草稿页面、附件上传和人工确认后的 OA 系统状态不能由本地 mock 完全证明。
- 历史生产数据迁移和 orphan task 清理必须先 dry-run，再由运维窗口执行；本地测试只能证明工具边界。
- deterministic Playwright 已覆盖 ETC 页面内三 bucket、business-batches 首屏暂时失败刷新恢复、未提交/已提交 business batch delete/reset 暂时失败重试恢复、source file delete 暂时失败重试恢复、ticket-root source upload 暂时失败重试恢复、OA draft 暂时失败重试恢复、草稿成功后暂存确认 target 保留、manual OA status 暂时失败重试恢复、未提交业务批次 -> OA 草稿暂存 -> 人工已提交 bucket 和成功后无可见错误残留；真实 OA 草稿页面、对象存储、Nginx 上传、大 ZIP、import confirm 等其它 mutation 级网络恢复，以及关联台、税金、成本 canonical 页面最终展示仍需跨模块 staging smoke。
- `tests/test_etc_backend.py` 已清零历史 `TemporaryDirectory(ignore_cleanup_errors=True)`；真实大 ZIP、对象存储/Nginx 上传、OA 和 worker drain 仍需要 staging/生产 smoke。

## 2026-07-22 Phase 27 ETC 普通写隔离回归

- ETC import、OA manual status、批次状态等普通写只提交 owner facts/version/audit 与精确 affected scope，不发布 Workbench/tax/cost 页面 refresh。
- `web/src/test/EtcTicketManagementPage.test.tsx` 与 `PageRouteHost.test.tsx` 覆盖：当前 ETC 页可在任务完成后重读；focus/visibility/BFCache 与旧业务事件不触发其它页面 load，route 重进/手动刷新走页面访问收敛。
- 显式 repair/reset/authoritative integration 仍按各自运维合同执行，不得被普通写零 fan-out 测试误删或降格。
