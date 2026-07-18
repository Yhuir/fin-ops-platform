# ETC票据管理 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/EtcTicketManagementPage.tsx` | unsubmitted/staged/submitted 三 bucket、summary 首屏、单次精确 detail、无 full task list/双 selection、明确 action disabled reason、OA intent idempotency、暂存确认/退回未提交、error/loading/delete dialog、OA 草稿后发票 PDF 下载、source file 和严格浏览器错误捕获 |
| Frontend API mapper | `web/src/features/etc/api.ts` | `/api/etc/business-batches*` 三 bucket/count/action envelope、精确 detail、OA recovery contract、发票 PDF blob/UTF-8 文件名、HTML/proxy error、multipart upload、stale preview error、本地化错误、旧 `/api/etc/batches*` 和 `/api/etc/invoices/revoke-submitted` API 不得回归 |
| Workbench UI | `web/src/components/workbench/CandidateGroupGrid.tsx` | `etc_invoice_summary` 折叠/展开、open/paired 区显示、撤回/删除后 summary 释放和已存在 canonical invoice 可见性 |
| HTTP routes | `server.py` `/api/etc*` | business batch、business batch title patch、reconciliation task、只读 invoice list、`invoice-pdf` 二进制响应/错误码/权限、import preview/confirm、source files、manual status、delete/reset 的状态码和结构化错误；慢解析期间 source file 被删除时必须返回 409 / `source_file_deleted_during_parse`；旧 `/api/etc/batches*`、`/api/etc/business-batches/{id}/oa-status/refresh`、`/api/etc/invoices/revoke-submitted` 不得回归 |
| Business service | `EtcService`、`EtcBatchInvoiceLinkService` | 业务批次幂等、标题持久化/版本/提交后锁定、状态流转、ETC metadata/附件占用释放、已存在 canonical invoice 关联、ETC batch invoice link 幂等写入、历史 batch 迁移、删除 audit |
| Application service | `EtcBusinessBatchApplicationService`、`EtcInvoicePdfBundleService` | OA 草稿、manual OA status、source file、绑定 task 恢复、发票 PDF scope/成员/排序/单页/大小/hash/审计、Workbench invalidation |
| Reconciliation service | `EtcReconciliationTaskService`、`CcbCreditCardStatementParser` | task ready/importing/imported/closed/deleted、source files、version、tombstone、重启 hydrate；信用卡 PDF 可选文字优先、图像型 PDF 布局 OCR fallback、OCR 人工核对 warning；解析提交与删除互斥、已删除来源拒绝提交、历史孤儿解析结果可审计清理 |
| Import worker | `ImportProcessingService`、runtime import worker | `etc_invoice_import` job、同 session 重试/幂等、后台导入成功后的 business batch 与 ETC metadata/附件关系保存，以及常驻 API 无需重启即可读取 worker 的 PostgreSQL 写入 |
| Workbench projection | `WorkbenchSqlProjectionBuilder`、`WorkbenchPairRelationService` | submitted business batch -> `etc_invoice_summary`、active relation 排除 open summary、submitted ETC 重叠正式发票不再作为普通 open invoice row、delete/reset 后不恢复旧 OA+银行二栏 relation |
| 运维工具 | cleanup/migration/repair tools | orphan task 清理必须显式 allowlist；历史迁移 dry-run/execute 不能绕过 service 边界；submitted ETC overlap 修复必须 dry-run-first 且 apply 需要 reason/operator |
| App Status | import worker、Workbench read model、App Health | import job、Workbench dirty/readiness、ETC route/API smoke、Nginx HTML/502 风险 |

## 关键 smoke flows

- 可选文字或图像型信用卡 PDF 上传 -> 文本解析或布局 OCR -> 票根文件上传 -> reconciliation task ready -> ETC ZIP preview -> confirm import job -> business batch visible -> OA draft -> manual submitted -> Workbench open 区出现 `etc_invoice_summary`。
- OA 草稿已创建 -> read-export 用户点击“下载发票PDF” -> `invoice-pdf` 读取 business batch 的 68 个 PDF -> 输出一份 68 页文件 -> 浏览器使用服务端 UTF-8 文件名保存；任一来源异常时不下载部分文件。
- Browser e2e：ETC 票据管理首屏 business-batches 暂时 503 -> 错误态且无普通空态 -> 点击刷新恢复未提交业务批次和发票明细；未提交业务批次删除第一次暂时 503 -> 错误可见且确认弹窗/批次行保持 -> 第二次成功后列表刷新为空；已提交业务批次 reset/delete 第一次暂时 503 -> expectedVersion/reason 使用已提交语义、错误可见且确认弹窗/已提交批次行/计数保持 -> 第二次成功后已提交列表刷新为空；source file 删除第一次暂时 503 -> 错误可见且确认弹窗/文件行保持 -> 第二次成功后文件列表刷新为空；ticket-root source upload 第一次暂时 503 -> 错误可见且不追加文件 -> 第二次成功后追加 TXT source file；创建 OA 草稿第一次暂时 503 -> 错误可见且不进入 OA 提交确认伪成功 -> dialog 保持可重试 -> 第二次成功；人工确认已提交第一次暂时 503 -> 错误可见且不切已提交 bucket -> OA 提交确认保持可重试 -> 第二次成功；未提交业务批次首屏 -> 展开发票明细 -> 创建 OA 草稿 -> 人工确认已提交 -> 已提交 bucket 展示人工确认状态；恢复、删除、上传、OA 草稿和人工确认成功后都检查无可见错误残留。
- 用户点击“新建批次” -> `POST /api/etc/business-batches` 可省略 `taskId` -> 后端创建 task + active business batch -> 未提交列表只显示返回的 business batch；若 business batch 创建失败，新建 task 必须 tombstone，不得留下刷新后复活的 task-only 批次。
- 用户在未提交列表点击批次标题 -> 内联编辑 -> `PATCH /api/etc/business-batches/{id}` 持久化 `title` 并同步 linked reconciliation task title -> ETC 发票导入页 ready task 下拉显示新标题；已提交批次标题不可编辑。
- business batch manual `not_submitted` -> 释放 ETC 发票占用 -> 回到未提交链路，不触发自动检测。
- 任意阶段 business batch delete/reset -> 删除本地导入和 task/source metadata -> 已提交 summary 消失；只有原本已存在于统一发票池的发票才可能回到普通发票视图。若 summary 已 active relation，取消 relation 且不恢复旧二栏关系。
- source file/object storage failure -> API 返回稳定 storage error -> 不留下半写入 source file、版本号或审计。
- source file 已落库 -> 慢 OCR 未完成时并发删除 -> 删除成功 -> OCR 提交返回 409 -> task 不包含孤儿 parse result/card item；历史孤儿按同一 `file_id` 删除后 formal file row 标记 `deleted`。
- failed/acknowledged/cancelled ETC import job -> 同 session 可重新 confirm；queued/running/recent succeeded 才允许幂等复用。
- 历史 ETC batch migration dry-run -> execute -> submitted bucket 可见 -> Workbench paired/open 口径一致。
- Nginx/API smoke -> `/api/etc/business-batches*` 必须返回 JSON，不得返回 HTML、502 或 React shell。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_import_service.py` | 覆盖信用卡 PDF 可选文字优先且不调用 OCR、图像型 PDF 布局 OCR 重建交易行和人工核对 warning；business batch title 空值拒绝、持久化、版本递增和提交后锁定，人工确认状态推进、历史缺 OA attempt 的 creating 批次只允许管理员依据 OA 主事实确认未创建后回到未提交且禁止采纳草稿、历史已提交业务批次创建、批次上报金额优先、ETC metadata 折叠规则、ETC 导入默认不创建 canonical invoice、已存在 canonical invoice 关联时强发票号 identity 优先于弱 fingerprint、任意阶段业务批次删除、已提交批次本地 reset 后 metadata 释放规则。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_import_service.py`、`tests/test_etc_batch_invoice_link_service.py`、`tests/test_postgres_core_repository.py`、`tests/test_postgres_state_store_integration.py`、`tests/test_historical_etc_business_batch_migration_service.py`、`tests/test_workbench_relation_command_service.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_pair_relation_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py`、`tests/test_repair_submitted_etc_invoice_overlaps_tool.py`、`tests/test_backfill_etc_batch_invoice_links_tool.py` | 覆盖 ETC business batch service 调用对账任务闭环、`EtcBusinessBatchApplicationService.create_batch_payload` 在省略 `taskId` 时创建 task + business batch 且创建失败会 tombstone 新 task、0101 形态历史任务经 0103 backfill 后与当前任务共同 hydrate/list/ready-list 的真实 PostgreSQL 回归、durable import job 活跃时对账任务不被启动恢复打断、runtime worker 从 `EtcImportResult.items` 回查 ETC metadata 且不创建 canonical invoice、北京速通信用卡项进入 ETC 候选并与同日同金额票根网 TXT 自动配对、无同窗口票根的信用卡项会按剩余同金额票根选择最近日期推荐配对、对账任务多候选时最大化一对一配对并按最近日期优先自动链接、业务批次已成功导入但 task 停在 ready 时创建 OA 草稿前的一致性补偿、ETC batch invoice link 幂等 upsert、历史 link backfill dry-run/apply/rollback 边界、历史迁移 service 编排、repository 落库金额/数量派生、审计、已提交批次 reset 链路、importing/closed/submission link 等任意阶段任务删除、删除后的 reconciliation task 以 `deleted` tombstone 防止部署重启复活、summary active relation 通过 Workbench relation command service 取消且不恢复旧 OA+流水二栏关系、历史 repair/existing link/historical migration 通过 command service 写 relation metadata，且缺少 command service 时 fail fast 不做本地半写入、submitted ETC overlap repair 的 dry-run/apply 边界、ETC OA 检测 worker/adapter 不再注册、旧 `EtcBusinessBatch` pickle 中已移除的 `oa_detection_status` 字段会被安全丢弃并补齐当前默认字段，以及对象存储失败时对账任务上传状态不留下半写入 source file。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖信用卡 PDF multipart 上传返回 source file、已解析 ETC 候选项和稳定 `parseIssues` 合同；`POST /api/etc/business-batches` 省略 `taskId` 时返回已绑定 task 和 title 的 business batch 且重启后 active business batch 持久可见、`PATCH /api/etc/business-batches/{id}` 更新 title并同步 linked task title、空标题和提交后锁定错误码、`manual-oa-status` 后响应、submitted bucket、兼容 `month` 筛选优先使用业务批次归属月份，缺失归属月份时按开票/通行日期匹配，且 counts 与 items 使用同一筛选口径、Workbench row shape、`DELETE /api/etc/business-batches/{id}` 对已提交批次返回本地 reset 结果、relation distribution stale 时仍通过 canonical relation command 删除 batch 并取消 summary relation、`DELETE /api/etc/reconciliation-tasks/{id}` 通过绑定业务批次执行同一删除链路、旧 task-only submission/import metadata 链路也不再返回 submitted confirmation guard、业务批次删除后重启不会重新出现在 `/api/etc/reconciliation-tasks`、ETC 导入确认失败 job 不阻塞同 session 重试、ETC `oa-status/refresh` 已移除且 business batch payload 不再输出 `oaDetection*` 字段、`/api/etc/invoices` route owner 只保留只读列表 I/O、`/api/etc/invoices/revoke-submitted` 已删除且 `EtcService` 不保留 invoice-id 级回退方法、ETC 票根网 TXT 上传支持 UTF-8/GB18030/GBK 文本并走 clipboard parser，以及 ETC 源文件上传在对象存储不可写时返回 `reconciliation_file_storage_unavailable`/503。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_etc_backend.py`、`tests/test_etc_reconciliation_service.py`、`tests/test_workbench_sql_runtime.py`、`tests/test_workbench_relation_command_service.py`、`tests/test_postgres_repositories_boundaries.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_background_job_service.py` | 覆盖 Workbench projection 从业务批次表生成 open `etc_invoice_summary`、匹配 OA 时追加汇总行、active relation 已存在时 open 区过滤陈旧 ETC summary、已提交批次 reset 后 summary 消失、包含 summary 的 active relation 取消后 OA/银行流水不恢复二栏配对，delete/reset 使用 canonical relation 写安全且不被 `workbench_relation` distribution non-fresh 阻断，durable ETC import job 活跃 session 阻止 task hydration recovery，failed/acknowledged/cancelled 导入 job 不被同 session 幂等复用，deleted reconciliation task 重启后不 rehydrate 且 Postgres formal file rows 被清理，runtime import worker 与 API import confirm 使用同一 ETC metadata/已存在 canonical invoice 关联口径，后台 job helper 等待 runner 完成后再释放测试数据目录，`tests/test_etc_backend.py` 已清零 `TemporaryDirectory(ignore_cleanup_errors=True)` 并用 API/service/import/Workbench 组合回归验证严格 cleanup，并验证展示金额与结构化 `amount_value`/numeric 金额列同时存在以支持金额搜索。 |
| 4a. Page Audit direct-canonical proof | 适用 | `tests/test_audit_etc_tickets_read_model_tool.py`、`tests/test_page_audit_registry.py`、`tests/test_app_health_api.py`、`web/src/test/PageAuditIcon.test.tsx` | 覆盖零 page read model 的诚实注册、统一 API dispatch、结构化列/registered payload、三 bucket count/active-key、creating 15 分钟门槛与 durable attempt、pending draft/submission、submitted/not-submitted occupancy、batch/task/file/invoice/import/submission typed edge、canonical invoice bridge、import queue 终态语义、只读 snapshot 和 UI direct-canonical success gate。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/CandidateGroupGrid.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/e2e/etc-tickets-flow.spec.ts`、`docs/modules/etc-tickets/e2e-spec.md`、`docs/modules/etc-tickets/e2e-coverage.md` | 覆盖单一批次列表、未提交/暂存/已提交三个 tab、页面无月份选择器且不发送 `month`、tab 计数与当前车牌/关键词筛选下的可见列表一致、未提交批次标题内联编辑并刷新 linked task title、business-batches 首屏暂时失败错误态、防普通空态和刷新恢复、页面初始化不读取 full task list、orphan reconciliation task 不进入业务批次列表、“新建批次”调用 `createEtcBusinessBatch({})` 而不是前端创建空 task、workflow 只按绑定 task 精确读取、人工确认按钮、草稿成功后即使 selection 迁移仍保留完整 batch/version 作为确认 target、确认后进入已提交或退回未提交、无自动检测入口、草稿创建失败 dialog 保持、OA draft 暂时失败可重试且不进入提交确认伪成功、manual OA status 暂时失败可重试且不切已提交 bucket、未提交 business batch delete 暂时失败可重试且不移除行/不关闭弹窗、已提交 business batch reset/delete 暂时失败可重试且不移除已提交行/不改变计数/不关闭弹窗、source file delete 暂时失败可重试且不移除文件/不关闭弹窗、ticket-root source upload 暂时失败可重试且不追加文件/成功后清除错误、前端 API/mock 不再暴露旧 `/api/etc/batches*`、`/api/etc/invoices/revoke-submitted` 或 ETC `oa-status/refresh`、任意阶段删除入口不因 OA/导入状态禁用、已提交批次删除确认文案、local reset 调用、ETC summary 展开明细按钮、大 ZIP 预览上传不会被普通 API timeout 提前截断，以及真实 Chromium 中三 bucket、PDF 下载、失败恢复、未提交 -> OA 草稿暂存 -> 人工已提交、严格浏览器错误捕获和成功后无可见错误残留的可见闭环。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py`、`web/e2e/etc-tickets-flow.spec.ts` | 覆盖导入/批次/人工提交/创建 OA 草稿/对账任务闭环/关联台展示/已提交批次本地 reset、任务入口删除绑定业务批次并取消 summary relation 的关键路径，并覆盖 durable import restart 后业务批次与 linked task 的一致性恢复；Playwright 补充真实浏览器 business-batches GET 暂时失败 -> 刷新 -> 恢复批次/明细、未提交 business batch delete 暂时失败 -> 弹窗/行保持 -> 重试成功后列表刷新、已提交 business batch reset/delete 暂时失败 -> submitted row/计数保持 -> 重试成功后列表刷新、source file delete 暂时失败 -> 弹窗/文件行保持 -> 重试成功后文件列表刷新、ticket-root source upload 暂时失败 -> 不追加文件 -> 重试成功后追加 source file、OA draft 暂时失败 -> dialog 保持 -> 重试成功、manual OA status 暂时失败 -> 保持提交确认 -> 重试成功，以及从未提交业务批次创建 OA 草稿到人工已提交 bucket 的页面闭环和成功后错误残留检查。 |
| 7. Existing feature regression tests | 适用 | `tests/test_etc_backend.py`、`tests/test_object_storage_repository.py`、`tests/test_oa_projection_sql_runtime.py`、`tests/test_mongo_oa_adapter.py`、`tests/test_postgres_migrations.py`、`tests/test_postgres_state_store_integration.py`、`tests/test_rabbitmq_staging_preflight.py`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/e2e/etc-tickets-flow.spec.ts` | 覆盖既有 ETC 页面旧入口、OA 匹配汇总行、删除/文件/补充凭证交互、OA projection/Mongo adapter 删除 ETC 专用候选查询后不影响非 ETC OA 能力、对象存储 repository 暴露 backend/bucket 给 PostgreSQL 文件写入，migration 清单连续且 0103 只从 typed 时间列幂等补齐缺失 payload 时间，RabbitMQ staging preflight 不再要求 ETC OA detection worker，防止首屏加载失败被伪装为空态、历史任务与新任务混排导致 list/ready-list 500、未提交/已提交 business batch delete/reset 暂时失败被伪装成已删除、source file delete 暂时失败被伪装成已删除、ticket-root source upload 暂时失败被伪装成已上传、OA draft 暂时失败被伪装成提交确认成功、manual OA status 暂时失败被伪装成已提交、旧撤销提交入口、旧检测入口、旧删除状态阻塞、浏览器层 OA 草稿确认流程和“成功但报错提示仍显示”重新漂移。 |

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
- 类别 5（前端）：`EtcTicketManagementPage.test.tsx` 覆盖 detail/task 并发、切换批次立即失效旧 mutation target、异步筛选列表自动选择新批次时同步失效旧 task 且旧 task mutation 请求为零、显式暂存行优先于旧 draft result，以及 manual status 成功后目标 bucket list 只发起一次 GET。
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
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_relation_command_service.py tests/test_historical_etc_business_batch_migration_service.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py::EtcApiTests::test_etc_summary_relation_cancel_delegates_to_workbench_relation_command_service tests/test_etc_backend.py::EtcApiTests::test_submitted_etc_business_batch_delete_uses_canonical_relation_when_read_model_is_stale -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py::EtcApiTests::test_historical_etc_repair_requires_relation_command_service_before_local_writes tests/test_etc_backend.py::EtcApiTests::test_existing_etc_batch_link_requires_relation_command_service_before_local_writes tests/test_historical_etc_business_batch_migration_service.py::HistoricalEtcBusinessBatchMigrationServiceTests::test_migration_requires_relation_command_service_before_business_batch_write -q
PYTHONPATH=backend/src python3 -m unittest tests.test_import_service tests.test_postgres_core_repository -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_rabbitmq_staging_preflight -v
PYTHONPATH=backend/src python3 -m unittest tests.test_postgres_migrations -v
FIN_OPS_TEST_DATABASE_URL=<disposable-postgres-url> PYTHONPATH=backend/src python3 -m pytest tests/test_postgres_state_store_integration.py::PostgresStateStoreIntegrationTests::test_timestamp_repair_restores_mixed_historical_and_current_task_lists -q
PYTHONPATH=backend/src python3 -m unittest tests.test_object_storage_repository tests.test_file_object_storage tests.test_etc_reconciliation_service -v
PYTHONPATH=backend/src python -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_matching_links_beijing_sutong_card_rows_to_ticket_root_txt_rows -q
PYTHONPATH=backend/src python3 -m unittest tests.test_background_job_service -v
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_batch_invoice_link_service.py tests/test_postgres_repositories_core.py::test_upsert_etc_batch_invoice_link_is_idempotent_by_batch_identity tests/test_postgres_migrations.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_repair_submitted_etc_invoice_overlaps_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_backfill_etc_batch_invoice_links_tool.py tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests::test_etc_invoice_summary_rows_prefer_link_table_source -q
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_closes_the_linked_reconciliation_task -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcServiceTests.test_business_batch_title_update_persists_and_locks_submitted tests.test_etc_backend.EtcApiTests.test_business_batch_title_patch_updates_linked_task_title -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_gb18030_txt_file_with_clipboard_parser -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_cascades_mutable_batch_contents tests.test_etc_backend.EtcApiTests.test_etc_business_batch_detail_returns_invoice_items_without_detection_fields tests.test_etc_backend.EtcApiTests.test_etc_business_batch_scope_uses_session_dept_id tests.test_etc_backend.EtcApiTests.test_etc_business_batch_oa_draft_waits_for_manual_confirmation_without_detection_runtime tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_files_append_to_reconciliation_task tests.test_etc_backend.EtcApiTests.test_etc_business_batch_source_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_etc_business_manual_status_accepts_confirmation_pending_state tests.test_etc_backend.EtcApiTests.test_etc_business_batch_submitted_list_counts_use_filtered_passage_month tests.test_etc_backend.EtcApiTests.test_historical_business_batch_lists_by_scope_month_and_reported_amount tests.test_etc_backend.EtcApiTests.test_etc_business_manual_submitted_creates_open_workbench_summary_with_reported_amount tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_releases_summary_and_deletes_local_task tests.test_etc_backend.EtcApiTests.test_legacy_submission_batch_delete_delegates_to_business_batch_reset tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_cancels_summary_relation_without_restoring_oa_bank_pair tests.test_etc_backend.EtcApiTests.test_etc_summary_relation_cancel_delegates_to_workbench_relation_command_service tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_uses_canonical_relation_when_read_model_is_stale tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_cancels_submitted_business_summary_relation tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_removes_orphan_submission_metadata_link tests.test_etc_backend.EtcApiTests.test_historical_etc_repair_reconcile_is_idempotent_from_seed_bundle tests.test_etc_backend.EtcApiTests.test_historical_etc_repair_requires_relation_command_service_before_local_writes tests.test_etc_backend.EtcApiTests.test_existing_etc_batch_link_extends_active_oa_bank_relation_and_renders_summary tests.test_etc_backend.EtcApiTests.test_existing_etc_batch_link_requires_relation_command_service_before_local_writes tests.test_etc_backend.EtcApiTests.test_existing_etc_batch_link_is_idempotent_and_does_not_create_parallel_relation -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_sql_runtime -v
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_deleted_task_does_not_rehydrate_from_postgres_retained_row_or_reuse_id tests/test_etc_backend.py::EtcApiTests::test_deleted_business_batch_route_tombstones_task_after_postgres_rehydrate tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_deleted_reconciliation_task_clears_formal_file_rows tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_uploaded_parse_result_rejects_source_deleted_before_parse_commit tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_delete_source_file_cleans_existing_orphan_parse_result tests/test_etc_backend.py::EtcApiTests::test_credit_card_statement_upload_rejects_parse_commit_after_source_deleted tests/test_etc_backend.py::EtcApiTests::test_delete_reconciliation_source_file_route_cleans_orphan_parse_result tests/test_postgres_repositories_boundaries.py::test_ops_tax_etc_multi_table_saves_use_transactions -q
python -m pytest tests/test_historical_etc_business_batch_migration_service.py tests/test_migrate_historical_etc_business_batches_tool.py
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

- 后端 ETC/API/service/import/workbench 投影组合：`tests.test_etc_backend`、`tests.test_etc_reconciliation_service`、`tests.test_import_service`、`tests.test_workbench_sql_runtime`、`tests.test_workbench_pair_relation_service`、`tests.test_platform_runtime_boundary_guards`、ETC cleanup/migration tool tests。
- 前端 ETC/API/Workbench summary 组合：`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/CandidateGroupGrid.test.tsx`。
- Playwright browser smoke：`web/e2e/etc-tickets-flow.spec.ts` 覆盖 business-batches 首屏暂时 503 -> 刷新恢复、未提交 business batch delete 暂时 503 -> 保持确认弹窗/批次行 -> 重试成功、已提交 business batch reset/delete 暂时 503 -> 保持确认弹窗/已提交批次行/计数 -> 重试成功、source file delete 暂时 503 -> 保持确认弹窗/文件行 -> 重试成功、ticket-root source upload 暂时 503 -> 不追加文件 -> 重试成功、OA draft 暂时 503 -> 保持 dialog -> 重试成功、manual OA status 暂时 503 -> 保持提交确认 -> 重试成功，以及未提交业务批次 -> OA 草稿 -> 人工已提交 bucket，并检查成功后无可见错误残留。
- `bash scripts/verify.sh docs`。

## 未测风险

- `tests.test_etc_backend` 中依赖本机真实票据样例的用例在样例缺失时会 skip；核心 ETC 业务批次和 Workbench projection 路径不依赖这些样例。
- ETC 票据管理已补 Spec-first E2E 合同和覆盖映射；本地 covered 不代表真实大 ZIP、对象存储、真实 OA、生产历史迁移或真实 worker drain 已完成。
- 真实大 ZIP、票根网 PDF/XML/TXT 混合包、Nginx 上传超时和对象存储权限仍需要 staging/生产前 smoke。
- 图像型信用卡 PDF 的 OCR 准确率依赖源文件分辨率、旋转和表格密度；自动测试已证明 fallback 与行结构，但真实扫描件仍必须根据 warning 核对行数、日期和金额。
- 真实 OA 草稿页面、附件上传和人工确认后的 OA 系统状态不能由本地 mock 完全证明。
- 历史生产数据迁移和 orphan task 清理必须先 dry-run，再由运维窗口执行；本地测试只能证明工具边界。
- deterministic Playwright 已覆盖 ETC 页面内三 bucket、business-batches 首屏暂时失败刷新恢复、未提交/已提交 business batch delete/reset 暂时失败重试恢复、source file delete 暂时失败重试恢复、ticket-root source upload 暂时失败重试恢复、OA draft 暂时失败重试恢复、草稿成功后暂存确认 target 保留、manual OA status 暂时失败重试恢复、未提交业务批次 -> OA 草稿暂存 -> 人工已提交 bucket 和成功后无可见错误残留；真实 OA 草稿页面、对象存储、Nginx 上传、大 ZIP、import confirm 等其它 mutation 级网络恢复，以及 Workbench、税金、成本和 search read model 全量重建后的最终页面展示仍需跨模块 staging smoke。
- `tests/test_etc_backend.py` 已清零历史 `TemporaryDirectory(ignore_cleanup_errors=True)`；真实大 ZIP、对象存储/Nginx 上传、OA 和 worker drain 仍需要 staging/生产 smoke。
