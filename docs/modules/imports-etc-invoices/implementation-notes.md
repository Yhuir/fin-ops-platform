# ETC发票导入 实施记录

## 2026-07-14：真实 59 ZIP 二次 504 与全局组合候选边界

- 部署首轮历史附件 read 优化后，使用 `发票5、6月.zip` 中 59 个真实、唯一且完整的内层 ZIP 复测；普通 parser 在本地 614ms 内解析 99 张发票、0 失败，但生产 multipart preview 上传约 24.98MB 后仍于 62 秒返回 Nginx 504。
- 初步把剩余延迟归因于 59 个串行 archive verified writes，并尝试最多 4 路并发。真实部署后 Nginx 仍在 61.918 秒返回 504，绕过 Nginx 的后端请求 300 秒仍不收敛；该方案已回滚，不作为最终实现。
- 回滚版绕过 Nginx 的串行请求同样在 240 秒未完成；本地使用生产 task payload 跑完整 `preview_etc_zip_for_task` 后，CPU 栈稳定落在多发票金额组合搜索。根因是 `_select_global_requirement_matches` 未像 sequential path 一样先按车牌与日期窗口过滤候选，导致 38 个需求分别在 99 张发票上构建大量无关组合，并存在跨车牌/日期误配风险。
- 修复由 `_requirement_match_options` 统一复用既有 `_invoice_satisfies_requirement_context`；精确金额组合改为按候选两半枚举并通过 `(张数, 金额)` 索引合并，只保留排序最优的 64 个精确组合，避免旧实现对每个候选复制并重排全部中间金额状态。不改变金额、发票张数、全局不重叠分配或 package-group 规则；并发 session store 改动撤销。新增跨车牌同金额组合与 30 候选/6 张发票回归，并使用同一真实 59 ZIP + 生产 task payload 做 task-aware 性能验证。
- release `main-7cbc77f64-etc59match-20260714` 使用同一 59 ZIP 通过公开 Nginx/API 入口完成 PostgreSQL + MinIO preview smoke：上传约 24.98MB，17.760 秒返回 HTTP 200；59 files / 99 items 中 68 included、31 excluded、0 blocking，应用性能样本 15.573 秒、505 次 SQL、数据库累计 1.649 秒。smoke 只持久化 preview session，没有 confirm；task version 19 仍为 `ready_for_import`、正式导入数 0。

## 2026-07-14：多 ZIP 预览 504 根因修复

- 生产只读证据显示已有 293 张 ETC 发票且附件为 MinIO object ref；task-aware preview 在两次 inspect 的 result/audit baseline 中逐张下载并 hash 校验 XML/PDF，共放大为 2344 次历史附件 SQL + MinIO 读取。59 个新 ZIP durable save 还会在 verified write 后同步重下载全部 archive，叠加 Nginx 默认 60 秒形成 504。
- 预览分类改用 verified MinIO/S3 object ref，不在请求热路径下载历史附件；真实导入写入仍保留 `_stored_invoice_file_exists` 检查，本地缺失附件修复语义不变。durable session 保存保留每个 ZIP 的 temporary/final 双写双读验证和 repository transaction，只删除提交成功后的冗余整批 readback。
- 新增 service 与 session store 回归，分别锁定“预览不探测 verified 历史附件”和“保存成功后不重下载 archive”；API shape、task/version/hash/fingerprint、worker 重载和对象写入校验合同不变。

## 2026-07-12：补齐 durable session file 运行角色权限

- 生产发布 0098 后，System Audit 首次读取 `app.etc_import_session_files` 暴露 `permission denied`；同一缺口也会阻断 API preview 的 replace/delete 和 worker confirm 的只读加载。
- 新增幂等 migration 0100：`fin_ops_app_runtime` / `fin_ops_api` / `fin_ops_migrator` 获得 session file 全 DML，worker/readonly 仅获得 select；不修改表结构和业务数据。
- 迁移 SQL 合同测试锁定完整角色矩阵，避免早期 `GRANT ... ALL TABLES` 被误认为会自动覆盖后续新表。

## 2026-07-11：durable preview、单一 worker confirm 与页面 Audit

- 识别真实生产缺口：旧 preview/session 只在 Web 进程 dict 中，独立 PostgreSQL worker 无法重载；route 仍保留 inline confirm 和旧直导 410 surface。
- 新增 `app.etc_import_session_files`，复用 `app.etc_import_sessions` / `app.file_objects`；metadata 与 bytes 分离，worker只依赖窄 session port。
- `begin_import` 移到 worker并对同 session 幂等；queue unavailable 不再先污染 task status。failed import job 可用同一 idempotency key受控重试并更新 background reference。
- 统一 Audit 升到 `page-audit-contract.v16`，本页从 unavailable 升为 ready；zero own read model，证明 ETC internal relations，不冒充 Workbench consumer。
- disposable PostgreSQL 0001–0098 验证 store 跨实例重载和 Audit destructive cases；未连接生产。



> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- ETC 发票导入不是通用发票导入的一种 batch type；它走 `/api/etc/import/preview`、`/api/etc/import/confirm`、reconciliation task 和 `etc_invoice_import.confirm` processor。
- ETC zip preview 的事实源是 confirmed reconciliation task 的版本和 `confirmed_item_set_hash`。task 或 canonical invoice 变化后必须重新预览，不能复用旧 session。
- ETC import confirm 后的事实源是 ETC business batch + ETC invoice metadata/PDF/XML 附件关系 + `etc_import_confirmed` lifecycle，不是 confirm API 或 background job 的返回值；该链路默认只关联已存在 canonical invoice，不创建新的统一发票池事实。
- 本模块首轮闭环状态为 `documented-risk`：自动化测试已覆盖核心 contract 和历史 bug，但真实大 zip、对象存储、真实 OA 草稿和真实 worker drain 仍需发布前验证。

## 记录模板

```markdown
## YYYY-MM-DD - <变更标题>

- 目标：
- 影响范围：
- 关键决策：
- 文档影响：
- 测试覆盖：
- 验证命令：
- 未测风险：
- 后续事项：
```

## 历史记录

## 2026-07-05 - runtime canonical cleanup surface 移出 ETC 导入主链路

- 目标：完成 ETC 发票导入模块边界 close，移除旧 ETC ZIP 直接创建 canonical invoice 后留下的 runtime cleanup surface，避免当前导入、删除或重导链路继续携带旧 `app.invoices` 清理 I/O。
- 影响范围：`EtcReconciliationImportCleanupService`、`EtcBusinessBatchDeleteService`、reconciliation imported-invoices 删除响应、`ImportNormalizationService` 和对应边界 guard；不改变 `/api/etc/import/preview`、`/api/etc/import/confirm`、`etc_invoice_import.confirm`、ETC metadata/附件持久化或下游 read model fan-out。
- 关键决策：ETC 导入模块只拥有 ETC task/import batch/business batch/metadata/PDF/XML 附件和 existing canonical invoice link 边界；删除导入结果时只返回 ETC 自有删除结果和 changed months，不返回 canonical 删除计数。历史 ETC-created canonical 污染不再挂在 runtime service 上，改由 `docs/operations/invoice-pool-cleanup.md` 的备份、dry-run、确认后清理流程处理。
- 文档影响：更新本模块 `README.md`、`boundary-io.md`、`state-machine.md`、`tests.md`、全局 testing closure dependency map 和本实施记录。
- 测试覆盖：更新 `tests/test_etc_reconciliation_import_cleanup_service.py`、`tests/test_etc_business_batch_delete_service.py`，删除旧 import service cleanup 单测，并扩展 `tests/test_platform_runtime_boundary_guards.py` 防止旧 canonical cleanup helper 回归。
- 验证命令：见本轮最终交付说明。
- 未测风险：未执行真实生产污染清理；如生产仍存在历史 ETC-created canonical 污染，必须按 invoice-pool cleanup runbook 单独备份、dry-run 和确认后处理。
- 后续事项：无模块 close 阻断；真实大 zip、对象存储、真实 worker drain 和 OA 草稿仍走 staging/发布前 smoke。

## 2026-07-03 - 导入文件事实列表摘要化

- 目标：修复生产 HTTP SLO 中 `/api/import-facts/files?page=1&page_size=50` 返回约 15MB 导致导入页探针超时的问题。
- 影响范围：`/api/import-facts/files`、`PostgresCoreRepository.list_import_files_page()`、默认 HTTP SLO probe；不改变 ETC 专用 `/api/etc/import/*` 预览、确认和 task 合同。
- 关键决策：导入文件事实列表是摘要 read API，只投影文件名、模板、状态、计数、批次 ID 和审计计数；完整 `raw_payload`、`row_results`、`normalized_rows` 只能保留在导入预览/session 边界，禁止旧 full payload 污染列表链路。
- 2026-07-05 后续修正：列表 repository 返回 summary dict，不再构造完整 `FileImportPreviewItem`；SQL 继续保留计数/batch/audit 摘要，但删除银行选择、识别结果和冲突消息等预览上下文 JSONB 提取。
- 文档影响：更新本模块 boundary、共享 persistence/read-model 边界、银行流水导入和发票导入 boundary。
- 测试覆盖：`tests/test_postgres_repositories_core.py::test_list_import_files_page_uses_summary_projection_without_raw_payload_blob`、`tests/test_import_file_api.py::ImportFileApiTests::test_import_fact_files_list_omits_preview_detail_payloads`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_import_file_api.py tests/test_postgres_repositories_core.py tests/test_http_slo_probe.py -q`。
- 未测风险：尚需发布后复跑生产 HTTP SLO，确认公网响应体和耗时已降到 1s 目标内。
- 后续事项：如果未来需要文件明细查看，应新增明确详情/下载 API，不得把预览明细重新放回列表。

## 2026-06-21 - ETC existing batch link工具收敛到统一链接服务

- 目标：移除 `link_existing_etc_batches.py` 中复制的 ETC 发票到统一发票池链接循环，避免运维工具绕过 `EtcExistingInvoiceLinkService` 后重新引入旧 canonical 同步逻辑。
- 影响范围：历史 existing ETC batch link 运维工具、`EtcExistingInvoiceLinkService` 和 runtime boundary guard；页面导入 API 口径不变。
- 关键决策：ETC ZIP/历史工具只允许把 ETC metadata 链接到已存在的 canonical `app.invoices`；工具原有的 `save_invoice_etc_metadata` 落库语义改为服务可选 `persist_linked_invoices` 回调，不在工具内保留本地 `upsert_etc_invoice` 循环。
- 文档影响：仅更新本实施记录；产品口径、API 契约和用户页面不变。
- 测试覆盖：新增/更新 runtime boundary guard，禁止运维工具绕过 `EtcExistingInvoiceLinkService`；新增服务测试覆盖已链接 invoice 的持久化回调。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py tests/test_link_existing_etc_batches_tool.py -q`；`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_existing_invoice_link_service.py backend/src/fin_ops_platform/tools/link_existing_etc_batches.py tests/test_platform_runtime_boundary_guards.py`。
- 未测风险：未执行真实 historical existing ETC batch link 工具 `--execute`；该路径仍需在生产备份后按运维 runbook 单独 dry-run/execute。

## 2026-06-21 - ETC import link-existing服务化

- 目标：让 ETC ZIP 导入完成后的 canonical invoice 关联逻辑只通过统一 service 执行，避免 API route 和 runtime worker 保留两份旧链接代码。
- 影响范围：`ImportProcessingService.execute_etc_invoice_import_confirm_job(...)` 的 runtime callback、`Application._link_etc_import_result_to_existing_invoices(...)` 和业务批次相关 link callback。
- 关键决策：`EtcExistingInvoiceLinkService` 是 ETC import result / ETC metadata 到已存在 `app.invoices` 的唯一链接边界；它不暴露 create invoice API，缺失 canonical invoice 时只返回 ETC 月份用于刷新，不创建统一发票池事实。
- 文档影响：本实施记录补充边界；ETC 导入 README 的“只关联已存在 canonical invoice，不创建新 canonical invoice”口径不变。
- 测试覆盖：boundary guard 强制 server/runtime helper 委托 service；runtime/service 行为测试覆盖按 `EtcImportResult.items[*].invoice_number` 回查 metadata、缺失 canonical invoice 不调用 create API。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_existing_invoice_link_logic_stays_out_of_server_and_worker_helpers tests/test_platform_runtime_boundary_guards.py::RuntimeWorkerEtcImportLinkExistingTests -q`。
- 未测风险：真实大 ZIP、对象存储、真实 worker drain 和生产 cleanup/reimport 仍需 staging/生产前 smoke。

## 2026-06-21 - ETC ZIP 额外发票 Drop 合同固化

- 目标：固定 ETC ZIP 只保存当前 reconciliation task 命中的 PDF/XML 附件和 metadata，防止 ZIP 内额外发票进入 `EtcService` state 或被误认为第二发票池。
- 影响范围：`EtcService._process_import_zips` 内部持久化入口、ETC import preview/confirm API 回归测试。
- 关键决策：route 层 `filter_uploads_by_allowlist` 负责裁剪 ZIP session；`EtcService` 内部持久化方法命名收缩为 `_upsert_attachment_metadata_from_import`，表达它只保存附件 metadata，不创建统一发票池事实。2026-07-05 起，历史污染清理不再挂在 runtime import service 上，改由 invoice-pool cleanup 运维链路处理。
- 文档影响：本实施记录补充合同；长期业务口径已在 `README.md`、`docs/product-specs/imports-and-etc.md` 和 `docs/operations/invoice-pool-cleanup.md` 维护。
- 测试覆盖：新增 `test_etc_import_drops_extra_zip_invoices_not_selected_by_current_task`，证明 task 只要求 `ETC001` 时，混合 ZIP 里的 `ETC999` 只出现在 preview exclusion 中，confirm 后不进入 ETC metadata，也不创建 canonical invoice。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py -k "drops_extra_zip_invoices or partial_success_when_some_items_fail or without_creating_canonical_invoices or confirmed_etc_submission_replaces_scatter_invoice" -q`；`PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_service.py tests/test_etc_backend.py`。
- 未测风险：真实对象存储、真实大 ZIP、真实 OA 草稿和生产 worker drain 仍需 staging/生产前 smoke；数据库内历史污染 canonical invoice 仍需按备份和 cleanup preflight 闭环处理。

## 2026-06-21 - ETC ZIP 不再创建统一发票池事实

- 目标：切断 ETC 专用导入链路向统一发票池自动创建 canonical invoice 的旧行为，避免 ETC ZIP 中的票据污染 `app.invoices`。
- 影响范围：`ImportNormalizationService.upsert_etc_invoice`、App/worker ETC sync helpers、ETC import confirm job、ETC summary row、历史 ETC repair/migration/link 和相关测试。
- 关键决策：ETC ZIP 的职责是保存命中当前 OA/业务批次的 PDF/XML 附件和 ETC metadata；只关联已存在的统一发票池记录，不在缺失时创建新发票。`ImportNormalizationService.upsert_etc_invoice` 不再保留 `allow_create` 后门；统一发票池仍由正式进/销项发票导入和受控 OA 附件识别创建。
- 文档影响：更新 `README.md`、`docs/modules/etc-tickets/README.md`、`docs/product-specs/imports-and-etc.md` 和 OA 集成模块记录。
- 测试覆盖：更新 ETC backend、historical migration、runtime worker link-existing 和 import service 测试，覆盖 ETC metadata 保留、summary 明细完整、缺失 canonical invoice 不创建、已存在 canonical invoice 仍可关联。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_etc_backend.py tests/test_historical_etc_business_batch_migration_service.py -q`；`PYTHONPATH=backend/src python3 -m pytest tests/test_import_service.py tests/test_invoice_attachment_recognition_service.py tests/test_platform_runtime_boundary_guards.py::RuntimeWorkerEtcImportLinkExistingTests -q`。
- 未测风险：真实生产 ZIP、对象存储和真实 OA 草稿附件上传仍需 staging/生产前 smoke；生产数据清理和重导入需先备份再执行。

## 2026-06-19 - ETC 导入成功路径 UI 错误残留 guard

- 目标：补齐 ETC 导入 Browser 成功链路的“假成功”检测，防止 confirm job 或下游 fresh 成功后页面仍残留导入失败、后台导入失败、read model 失败等提示。
- 影响范围：`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/fixtures/successAssertions.ts`、Playwright 严格诊断静态测试和本模块测试文档。
- 关键决策：只加固 deterministic Browser E2E 和静态 guard，不改产品逻辑；preview 中的 XML 解析失败是文件级 preview 证据，不纳入成功残留错误模式。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：ETC import confirm job 成功、ETC 票据、税金抵扣和成本统计 fresh 成功节点都会调用 `expectNoUnexpectedSuccessUiErrors`。
- 验证命令：`cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts e2e/imports-invoices-flow.spec.ts e2e/imports-etc-invoices-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实大 zip、票根网/PDF/XML/TXT 混合包、对象存储、真实 OA 草稿、真实 import/derived lifecycle worker drain、Workbench/search/historical repair 最终 fresh 仍需 staging 或生产只读 smoke。
- 后续事项：新增 search Browser route、历史修复页面入口或新 ETC 模板时，把成功后错误残留 guard 加入对应 Browser flow。

## 2026-06-19 - ETC 导入 Spec-first covered 校准

- 目标：完成 `/imports/etc-invoices` 本地 Spec-first E2E Audit 校准，把剩余 `IMPORT-ETC-E2E-004` 和 `IMPORT-ETC-E2E-010` 从 partial 收敛为 covered，并把真实对象存储/worker/OA 草稿风险保留在 `IMPORT-ETC-E2E-011` external-risk。
- 影响范围：ETC 导入 Spec-first 覆盖矩阵、全局 Spec-first inventory、testing closure state 和本实施记录；不改产品逻辑。
- 关键决策：当前 Browser 已覆盖 ready task、zip preview、included/duplicate/attachment_completed/failed 文案、preview stale、stale reconciliation task preview、confirm 失败、background job feedback、权限 gate，并覆盖 ETC 票据、税金抵扣和成本统计 downstream fresh read model 展示。missing requirements 由组件/后端覆盖；Workbench/search/historical repair scope 由后端 contract 和 staging gate 保护，search 当前无独立前端 route。
- 文档影响：`IMPORT-ETC-E2E-004` 和 `IMPORT-ETC-E2E-010` 标记为 `covered`；全局 inventory 和 testing closure state 可将 `imports-etc-invoices` 从 `partial` 校准为 `covered`。
- 测试覆盖：未新增测试；基于现有 `web/e2e/imports-etc-invoices-flow.spec.ts`、`permissions-role-matrix`、ETC API/service/lifecycle/read model 和 write-operation SLO audit contract 证据校准。
- 验证命令：待本轮运行三类导入 Playwright specs、`bash scripts/verify.sh docs` 和 `git diff --check`。
- 未测风险：真实大 zip、票根网/PDF/XML/TXT 混合包、对象存储、真实 OA 草稿、真实 import/derived lifecycle worker drain、Workbench/search/historical repair 最终 fresh 仍需 staging 或生产只读 smoke。
- 后续事项：新增独立 search Browser route、历史修复页面入口或新 ETC 真实模板时，按功能追加 Browser E2E；真实 worker 最新性走 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=etc_import_confirmed bash scripts/verify.sh infra-smoke`。

## 2026-06-19 - ETC 导入下游 fresh read model Browser fan-out

- 目标：补齐 `IMPORT-ETC-E2E-010` 的 Browser 证据，避免 ETC 导入只证明 confirm job queued，而没有证明下游页面能读取 fresh read model。
- 影响范围：deterministic Playwright mock、`web/e2e/imports-etc-invoices-flow.spec.ts`、ETC 导入模块 Spec-first 覆盖矩阵。
- 关键决策：不改产品逻辑；mock 增加 `etcImportDownstreamFanout`，只有 ETC confirm 成功后才让 ETC 票据批次、税金抵扣和成本统计暴露导入证据；Browser 用例等待下游 GET 响应并断言 `read_model_status=fresh`。
- 文档影响：更新 `e2e-coverage.md` 和 `tests.md`，把真实 worker drain、Workbench/search/historical repair 仍保留为 staging/documented risk。
- 测试覆盖：新增 ETC 导入 Browser flow，覆盖 confirm -> ETC ticket business batch -> tax offset fresh row -> cost statistics fresh project/transaction evidence。
- 验证命令：`cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium`。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd import worker、derived lifecycle worker、真实对象存储/OA 草稿、Workbench/search/historical repair 最终 fresh 仍需 staging 或生产只读 smoke。

## 2026-06-19 - ETC 导入真实 write-flow SLO audit profile

- 目标：补齐 ETC 导入 Spec-first E2E 闭环中的真实 read model/worker 证据入口，避免只用 deterministic Browser mock 或直接 enqueue smoke 声称真实写链路已闭环。
- 影响范围：`write_operation_slo_audit`、ETC 导入测试矩阵、`IMPORT-ETC-E2E-011` 真实基础设施 gate。
- 关键决策：profile 名使用业务规格 `etc_import_confirmed`，但匹配真实 durable queue reason `etc_invoice_import_confirm`；search 是 cache clear，不属于该工具审计的 `*.read_model.refresh` 事件。
- 覆盖 scope：Workbench、Workbench relation、invoice lifecycle、tax offset 和 cost statistics。
- 测试覆盖：新增 `tests/test_write_operation_slo_audit.py` 回归，验证完整 scope 才通过，缺少税金抵扣等下游 scope 时必须失败。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_slo_audit -v`；`bash scripts/verify.sh docs`；`bash scripts/verify.sh infra-smoke`。
- 未测风险：本地契约测试不产生真实 ETC confirm outbox rows；仍需 staging/发布前运行 `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit --json --operation etc_import_confirmed --lookback-hours 24`，并配合真实对象存储/OA 草稿/import worker/read model worker 和下游页面最终 fresh 检查。

## 2026-06-19 - ETC 导入 Spec-first Browser 负面路径

- 目标：把 `/imports/etc-invoices` 从单一 happy path Browser smoke 提升为 Spec-first E2E 基线，覆盖 `preview_stale`、`stale_reconciliation_task_preview` 和 confirm failure，防止页面在旧 preview、task 变更或 confirm 失败时仍展示后台导入成功。
- 影响范围：deterministic Playwright mock、`web/e2e/imports-etc-invoices-flow.spec.ts`、ETC 导入模块 Spec-first E2E 文档和全局测试闭环状态。
- 关键决策：不改产品逻辑；复用 ETC API mapper 的固定 stale 文案，只在 mock 中增加 ETC 导入专用失败开关。mock confirm job queued 不等同于真实 worker drain，真实 PostgreSQL/RabbitMQ/Redis/systemd worker、对象存储、OA 草稿和下游 read model freshness 仍作为 `external-risk` 记录。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、全局 Spec-first inventory、测试说明和闭环状态。
- 测试覆盖：Browser E2E 覆盖 ready task、zip preview、audit、异常/重复/附件补齐明细、confirm job feedback、`preview_stale` 无 job success、`stale_reconciliation_task_preview` 清空旧 preview 并禁用 confirm、confirm 500 无 job success，且全部断言不走通用 `/imports/files/*`。
- 验证命令：见本轮最终交付说明。
- 未测风险：真实票根网 zip、大 zip、对象存储、真实 OA 草稿、真实 import worker drain、derived lifecycle worker、Workbench/tax/cost/search read model 最终 fresh 仍需 staging 或生产只读 smoke。
- 后续事项：继续补真实基础设施 worker drain smoke，或补 ETC 导入后的下游多页面 Browser fan-out。

## 2026-06-16 - ETC 导入合成混合 zip 预览守护

- 目标：为 P2/P3 ETC 大 zip、重复票号和坏 XML 风险补本地可重复证据，避免混合包 preview 因单个坏文件中断或把重复/失败计数混入有效导入。
- 影响范围：`EtcService.preview_import_zips`、ETC zip parser/audit、ETC 发票导入测试矩阵。
- 关键决策：不改 ETC 导入行为；使用 120 张合成 ETC 发票、PDF 附件、同包重复 XML 和 malformed XML 锁定 preview contract：有效发票、duplicatesSkipped 和 failed item 分离计数，preview 不持久化发票记录。
- 文档影响：更新 `tests.md` 的场景覆盖、历史 bug 回归和未测风险；P2/P3 台账记录为 local synthetic evidence。
- 测试覆盖：新增 `test_preview_large_mixed_zip_keeps_valid_invoices_duplicates_and_failures_separate`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcServiceTests.test_preview_large_mixed_zip_keeps_valid_invoices_duplicates_and_failures_separate -v`；本轮也与银行/发票合成导入测试一起运行通过。
- 未测风险：真实票根网 zip、PDF/XML/TXT 混合包、对象存储、Nginx 上传限制、真实 OA/worker drain 和浏览器上传耗时仍需 staging/manual smoke。
- 后续事项：拿到用户批准的真实 ETC 样本后，在 staging 跑 preview/confirm/object-storage/Nginx/job/read-model smoke，不在仓库保存真实业务文件。

## 2026-06-16 - ETC 导入 App Status job metadata 闭环

- 目标：关闭 ETC 导入 confirm 后 background job 缺少 task/domain/route 元数据的风险，让全局状态能稳定指向 `/imports/etc-invoices` 并标记 `etc_tickets` 受影响。
- 影响范围：`/api/etc/import/confirm` 的 `etc_invoice_import` background job source、ETC 导入 API contract regression、模块状态机和测试矩阵。
- 关键决策：ETC 导入仍使用专用 `/api/etc/import/*` 和 `etc_invoice_import.confirm` processor；job type 已有 registry 默认值，但具体 job source 也持久化 `task_id`、`affected_domains` 和 `route`，便于 App Status、审计和后续排障。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`，并在 Phase17 GSD 产物记录本次闭环。
- 测试覆盖：更新 ETC confirm API regression，覆盖 job type、domain、route、source task、异步导入和下游发票可见。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_confirm_returns_background_job_and_imports_asynchronously -v`；扩展后端 302 tests；前端 ETC/导入/App Status 111 tests；`bash scripts/verify.sh docs`。
- 未测风险：真实大 zip/票根网/PDF/XML 混合包、真实对象存储、真实 OA 草稿、真实 Postgres/RabbitMQ/Redis/systemd import worker drain、Nginx 代理和大数据浏览器 smoke。
- 后续事项：17 个页面 phase 完成后做最终跨 phase 状态和 diff sanity check。

## 2026-06-11 - ETC 发票导入测试闭环首轮

- 目标：补齐 `/imports/etc-invoices` 的影响面、七类测试矩阵、状态机、历史 bug 回归库和验证命令。
- 影响范围：共享 `ImportWorkflowPage`、ETC API mapper、`/api/etc/import*`、reconciliation task、zip parser/filter、ETC service、import worker、business batch、existing canonical invoice link、`etc_import_confirmed` lifecycle、关联台、税金抵扣、成本统计、搜索和 App Status。
- 关键决策：不新增低价值测试；先把现有 ETC backend/reconciliation/API/frontend/business-batch 测试登记到模块矩阵，并把真实基础设施/真实 OA 风险标记为 `documented-risk`。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`docs/dev/testing-closure-dependency-map.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：覆盖七类测试；重点保护 ready task gate、zip preview filter、stale task preview、async confirm job、existing canonical invoice link、business batch summary 和下游 read model refresh。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实大 zip/票根网/PDF/XML 混合包、真实对象存储、真实 OA 草稿、真实 Postgres/RabbitMQ/Redis/systemd import worker drain、Nginx 代理和大数据浏览器 smoke。
- 后续事项：后续模块处理 `output-invoice-collections`；另行专项校准共享 `import.process.requested` App Status affected domain。
