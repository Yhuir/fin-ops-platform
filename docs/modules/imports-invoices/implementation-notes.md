# 发票导入 实施记录


> 本文件只保存提炼后的实施记录，不保存原始 Codex prompt、阶段性闲聊或临时探索日志。完成后的长期事实应沉淀到 `README.md`、`state-machine.md`、`tests.md` 或对应长期事实源。

## 当前决策

- 发票导入不是独立实现；页面入口复用 `ImportWorkflowPage mode="invoice"`，因此任何共享导入工作流改动都必须同时检查银行流水导入和 ETC 发票导入。
- 发票导入确认后的事实源是 canonical invoice facts + derived lifecycle + read model freshness，不是 confirm API 或 background job 的返回值。
- 本模块首轮闭环状态为 `documented-risk`：自动化测试已覆盖核心 contract 和历史 bug，但真实大文件、真实 Postgres/RabbitMQ/Redis/systemd worker drain、下游页面真实浏览器 smoke 仍需发布前验证。

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

## 2026-07-22 - stale preview 覆盖已确认导入修复

- 目标：修复 API 进程持有旧 preview 内存时，后续预览其它文件把 worker 已确认的发票 batch/file/session 覆盖回 `pending/preview_ready`。
- 关键决策：删除无 session 范围的 preview 全量 snapshot writer；preview/retry 只写当前 session 与 `preview_batch_id`，不携带 canonical facts。PostgreSQL import/file delta 复用现有 repository transaction 同时提交。
- 测试覆盖：session-scoped payload、跨进程 stale API 回归、计数器单调、PostgreSQL 半写回滚和旧 writer 架构守卫。
- 文档影响：仅更新发票与银行共享导入边界；API、App Health、worker registry 和 read model 合同不变。

## 2026-07-11 - 发票导入 direct-canonical Audit 与 durable confirm 单链闭环

- 目标：使 `imports.invoices` 能证明全部已登记 App 内部导入事实，同时删除绕过 durable queue 或制造不可逆半状态的旧路径。
- 关键决策：页面没有 own read model，也不消费业务配对关系；Audit 在一个只读一致性快照内比较 file/session/batch/row、canonical invoice 和 `(invoice_id,batch_id,source_id)` manual source-link 集合，并重算 counts/关键发票字段。下游 Workbench/lifecycle/tax/cost 等只登记为 impacts。
- 旧链删除：file confirm 不再 inline 执行；PostgreSQL/RabbitMQ 均通过 `job.import_jobs + job.outbox_events`，queue 缺失 fail closed。删除无正式 caller 且无法完整撤销 merge/source-link 的 batch revert；migration 0097 删除无 writer 的 `app.import_files.import_batch_id`。
- 验证：fake/protocol、API/worker、runtime guard、Vitest，以及 disposable PostgreSQL 全迁移 clean + field/source-link/hash/job/outbox 破坏性验证通过；未连接生产。
- 保证边界：通过只证明 App 已登记导入合同；不能证明税务平台导出未漏票，也不能替代下游每页 Audit。

## 2026-07-03 - 导入文件事实列表摘要化

- 目标：修复生产 HTTP SLO 中 `/api/import-facts/files?page=1&page_size=50` 返回约 15MB 导致导入页探针超时的问题。
- 影响范围：`/api/import-facts/files`、`PostgresCoreRepository.list_import_files_page()`、默认 HTTP SLO probe；不改变 `/imports/files/*` 上传、预览、确认和 session detail 合同。
- 关键决策：导入文件事实列表是摘要 read API，只投影文件名、模板、状态、计数、批次 ID 和审计计数；完整 `raw_payload`、`row_results`、`normalized_rows` 只能保留在导入预览/session 边界，禁止旧 full payload 污染列表链路。
- 2026-07-05 后续修正：列表 repository 返回 summary dict，不再构造完整 `FileImportPreviewItem`；SQL 继续保留计数/batch/audit 摘要，但删除银行选择、识别结果和冲突消息等预览上下文 JSONB 提取。
- 文档影响：更新本模块 boundary、共享 persistence/read-model 边界、银行流水导入和 ETC 导入 boundary。
- 测试覆盖：`tests/test_postgres_repositories_core.py::test_list_import_files_page_uses_summary_projection_without_raw_payload_blob`、`tests/test_import_file_api.py::ImportFileApiTests::test_import_fact_files_list_omits_preview_detail_payloads`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_import_file_api.py tests/test_postgres_repositories_core.py tests/test_http_slo_probe.py -q`。
- 未测风险：尚需发布后复跑生产 HTTP SLO，确认公网响应体和耗时已降到 1s 目标内。
- 后续事项：如果未来需要文件明细查看，应新增明确详情/下载 API，不得把预览明细重新放回列表。

## 2026-06-23 - ETC 批次发票 link table 最小接入

- 目标：把正式发票导入后的 submitted ETC metadata 回挂从单纯 `etc_invoice_id/raw_payload` 扩展为 `app.etc_batch_invoice_links` 批次归属事实，开始收敛“一张真实发票一行 canonical invoice、批次关系进 link table”的长期架构。
- 影响范围：新增 `EtcBatchInvoiceLinkService`、PostgreSQL link table migration/repository upsert、`ImportNormalizationService` 反向链接路径、关联台 open invoice SQL 排除路径。
- 关键决策：导入服务在严格匹配 submitted/manual-submitted ETC metadata 后仍会写入兼容 metadata，但同时通过 link service 幂等 upsert `tenant_id + business_batch_id + identity_key` 的 active link。未执行历史 backfill，因此旧数据仍由 Phase A 兼容查询保护。
- 文档影响：同步 Phase 18 GSD 和 ETC/关联台模块；reset/backfill/runbook 留到 Phase C。
- 测试覆盖：新增 `tests/test_etc_batch_invoice_link_service.py`、migration/repository upsert 测试，并更新导入反向链接测试要求写 link table。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_import_service.py tests/test_etc_batch_invoice_link_service.py tests/test_postgres_repositories_core.py::test_upsert_etc_batch_invoice_link_is_idempotent_by_batch_identity tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests tests/test_postgres_migrations.py -q`。
- 未测风险：尚未执行生产 migration/backfill/apply；真实库现有 overlap row set 仍需 Phase C dry-run/backfill 后才能完全切到 link table。
- 后续事项：Phase C 增加 backfill/rollback 工具，并更新清空发票池 runbook。

## 2026-06-23 - 已提交 ETC 批次后的正式发票导入反向链接

- 目标：修复历史 ETC 批次先存在、随后清空/重建发票池并导入正式进项发票时，同一真实发票同时作为 ETC 批次明细和普通 open 发票出现在关联台的问题。
- 影响范围：`ImportNormalizationService` 正式发票 upsert 后的 metadata 合并、PostgreSQL 发票 identity 查询、关联台 open invoice SQL 投影，以及 dry-run-first 生产修复工具。
- 关键决策：`app.invoices` 仍是一张真实发票一行的 canonical pool；Phase A 不新增 schema，而是在正式发票导入后按强身份查找 submitted/manual-submitted ETC metadata，只有发票号、日期、金额、税额、购销方等严格匹配时才把 ETC metadata 回挂到 canonical invoice 并隐藏其 open 发票视图。ETC ZIP/批次导入本身仍不得创建新的 canonical invoice。
- 文档影响：同步发票导入、关联台和 ETC 票据模块记录；Phase B 会继续把批次归属迁到 `app.etc_batch_invoice_links`。
- 测试覆盖：新增 `tests/test_import_service.py::ImportNormalizationServiceTests::test_input_invoice_import_links_existing_submitted_etc_metadata_when_formal_invoice_arrives_later`，并配合 repository、Workbench SQL 和修复工具测试覆盖同一生产事故形状。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_import_service.py tests/test_postgres_repositories_core.py::test_find_submitted_etc_invoice_by_identity_returns_active_batch_metadata tests/test_workbench_sql_runtime.py::WorkbenchSqlProjectionRelationPayloadTests tests/test_repair_submitted_etc_invoice_overlaps_tool.py -q`。
- 未测风险：尚未执行生产 `--apply`；当前真实库 dry-run 仍有 112 条自动修复候选和 1 条日期不一致人工判定候选，必须经用户确认 exact row set、reason、operator 和回滚方式后才能写库。
- 后续事项：Phase B 新增 `app.etc_batch_invoice_links` 后，把反向链接从 `etc_invoice_id/raw_payload` 过渡到 link table 事实源。

## 2026-06-21 - 导入 preview/confirm 轻量化与批量查重

- 目标：修复发票导入 preview/confirm/read model 链路中的两个性能瓶颈：preview/confirm 每行远程查重，以及 preview 保存整份 workbench 关系快照并触发 read model 刷新。
- 当时影响范围包含 legacy `/imports/preview`；该入口已于 2026-07-11 删除。当前范围只保留文件 `/imports/files/preview`、导入 confirm job 持久化、PostgreSQL invoice identity repository、下游 read model enqueue；不改变发票 identity 规则、重复判定语义或 confirm 后写入的 canonical invoice facts。
- 关键决策：preview 只保存 `imports` 与 `file_imports` 的预览/session 状态，不刷新 Workbench、pending invoice、invoice usage、search、cost 等 read model。confirm 前仍会重新校验当前 DB 状态，但同一批次使用一次 bulk identity preload，避免逐行 DB 往返。confirm 后使用轻量 import-state persistence，只保存 import/file/ETC/tax import 状态并通过 read model gateway 投递必要 scopes，不再持久化整份 `workbench_pair_relations` snapshot。
- 文档影响：本实施记录和 `tests.md` 已同步；长期 API shape 不变。
- 测试覆盖：新增/更新 `tests/test_import_service.py`、`tests/test_postgres_repositories_core.py`、`tests/test_import_file_api.py`，覆盖批量发票 identity preload、PostgreSQL bulk lookup、文件 preview 不调用重型 workbench persistence。
- 验证命令：`pytest -q tests/test_import_service.py tests/test_postgres_repositories_core.py tests/test_import_file_api.py tests/test_import_processing_service.py`。
- 未测风险：本地测试证明代码边界和查询形态，不替代真实生产大文件上传、RabbitMQ/worker drain、Redis cache 或浏览器手工导入 smoke。清空发票池后需要由用户重新手工导入 371+20 文件验证完整链路。
- 后续事项：真实手工导入后只读观察 `app.invoices` 计数、read model queue drain、下游页面 freshness 和 App Health，确认没有长期 `processing/refreshing`。

## 2026-06-20 - 发票导入 read model 刷新链路收敛

- 目标：针对真实发票导入后“关联台可逐步看到新增/更新发票，但全局状态长期同步中”的问题，修复 runtime queue/worker 闭环并降低导入 fan-out。
- 影响范围：发票导入确认后的 `import_state_changed` fan-out、下游 pending invoice/workbench read model refresh、银行流水导入兼容的 `bank_detail` refresh bridge；不改变发票解析、重复判定或 canonical invoice 写入语义。
- 关键决策：用户看到关联台新增发票不等于 read model 链路完成；导入成功必须以后端 dirty/outbox/readiness 全部收敛为准。`save_imports` 只保存完整 facts snapshot，不再从全量 snapshot 推导 `import.fact.changed`；发票导入不应产生 `import_facts_changed` 旁路。pending invoice 在有影响月份时直接投递月级 scope，避免全量 aggregate 先展开再刷新。银行流水导入的银行明细刷新由本次导入行计算月份并投递真实 `bank_detail.read_model.refresh`，兼容 `import.fact.changed` handler 也只作为 legacy bridge 投递真实 refresh 后完成兼容 dirty scope。runtime queue 的 superseded 判定新增创建顺序约束，避免历史高 `source_version` done event 覆盖当前导入产生的新 event。
- 后续优化：发票导入已进一步支持方向级 fan-out；进项文件只投递 `input_invoice_usage`，销项文件只投递 `output_invoice_collection`，混合导入按各自文件月份分别投递。`write_operation_slo_audit` 中这两个方向页为可选命中项，缺少未命中方向显示 `skipped`，不再误判 input-only/output-only 导入失败。
- 文档影响：同步 runtime-workers 与 read-models 模块记录；本模块真实基础设施 gate 仍需发布后执行。
- 测试覆盖：`tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_does_not_let_older_done_event_cover_newer_processing_event`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_processing_service.py::test_file_import_confirm_job_returns_import_write_targets`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_import_fact_changed_handler_completes_matching_dirty_scope`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate`、`tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_skips_unaffected_invoice_relation_read_models`、`tests/test_write_operation_slo_audit.py::WriteOperationSloAuditTests::test_invoice_import_confirmed_profile_allows_direction_specific_relation_refresh`。
- 验证命令：`PYTHONPATH=backend/src python3 -m pytest tests/test_runtime_queue.py tests/test_runtime_worker.py tests/test_runtime_monitoring.py tests/test_import_job_queue.py tests/test_runtime_worker_registry.py tests/test_read_model_refresh_gateway.py tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests::test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests/test_write_operation_slo_audit.py -q`。
- 未测风险：本地测试不连接真实生产 RabbitMQ/Redis/systemd worker；发布后必须只读观察本次导入相关 outbox/dirty/readiness 是否归零，并用小批量发票重新导入跑 `invoice_import_confirmed` write-operation SLO audit。

## 2026-06-19 - 发票导入成功路径 UI 错误残留 guard

- 目标：补齐发票导入 Browser 成功链路的“假成功”检测，防止 confirm 或下游 fresh 成功后页面仍残留导入失败、后台导入失败、read model 失败等提示。
- 影响范围：`web/e2e/imports-invoices-flow.spec.ts`、`web/e2e/fixtures/successAssertions.ts`、Playwright 严格诊断静态测试和本模块测试文档。
- 关键决策：只加固 deterministic Browser E2E 和静态 guard，不改产品逻辑；损坏文件 file-level error 和未导入项明细仍是合法 preview 结果，不纳入成功残留错误模式。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：发票导入 confirm 成功、草稿清空，以及销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计 fresh 成功节点都会调用 `expectNoUnexpectedSuccessUiErrors`。
- 验证命令：`cd web && npx playwright test e2e/imports-bank-transactions-flow.spec.ts e2e/imports-invoices-flow.spec.ts e2e/imports-etc-invoices-flow.spec.ts --project=chromium`；`PYTHONPATH=backend/src python3 -m unittest tests.test_playwright_e2e_strict_diagnostics -v`；`bash scripts/verify.sh docs`。
- 未测风险：真实发票大文件/历史模板/信息汇总表样本、真实 import/derived lifecycle worker drain、worker crash/retry、search 外层 UI 和真实下载/大表 smoke 仍需 staging 或生产只读 smoke。
- 后续事项：新增导入进度 UI、search Browser route 或发票模板时，把成功后错误残留 guard 加入对应 Browser flow。

## 2026-06-19 - 发票导入 Spec-first covered 校准

- 目标：完成 `/imports/invoices` 本地 Spec-first E2E Audit 校准，把剩余 `IMPORT-INVOICE-E2E-008` 从 partial 收敛为 covered，并把真实 worker drain 保留在 `IMPORT-INVOICE-E2E-009` external-risk。
- 影响范围：发票导入 Spec-first 覆盖矩阵、全局 Spec-first inventory、testing closure state 和本实施记录；不改产品逻辑。
- 关键决策：当前 Browser 已覆盖上传/预览/慢预览锁定、重复与未导入明细、损坏文件混合、preview stale、confirm 失败、权限 gate、显式 operation barrier 等待和零 Workbench 页面请求，以及销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计自身的 fresh read model 与导入影响行。search 当前无独立前端 route，由 API/runtime 证据覆盖；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实信息汇总表和大文件仍归 `IMPORT-INVOICE-E2E-009`。
- 文档影响：`IMPORT-INVOICE-E2E-008` 标记为 `covered`；全局 inventory 和 testing closure state 可将 `imports-invoices` 从 `partial` 校准为 `covered`。
- 测试覆盖：未新增测试；基于现有 `web/e2e/imports-invoices-flow.spec.ts`、`permissions-role-matrix`、导入 API/service/lifecycle/read model 和 write-operation SLO audit contract 证据校准。
- 验证命令：待本轮运行三类导入 Playwright specs、`bash scripts/verify.sh docs` 和 `git diff --check`。
- 未测风险：真实发票大文件/历史模板/信息汇总表样本、真实 import/derived lifecycle worker drain、worker crash/retry、search 外层 UI 和真实下载/大表 smoke 仍需 staging 或生产只读 smoke。
- 后续事项：新增独立 search Browser route、导入进度 UI 或新发票模板时，按功能追加 Browser E2E；真实 worker 最新性走 `FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS=invoice_import_confirmed bash scripts/verify.sh infra-smoke`。

## 2026-06-19 - 发票导入下游 fresh read model Browser fan-out

- 目标：补强 `IMPORT-INVOICE-E2E-008`，让发票导入确认后的 Browser 回归不只验证 Workbench、销项收款、进项使用和税金抵扣，还继续覆盖待找发票、OA 待付款和成本统计的 fresh read model 展示。
- 影响范围：`web/e2e/imports-invoices-flow.spec.ts`、deterministic API mock、发票导入模块 Spec-first 覆盖文档和全局 testing closure state。
- 关键决策：不改产品逻辑；新增发票导入专用 deterministic mock 行，不复用 `workbench_relation` 的 confirmed/candidate 语义，避免把导入 lifecycle fan-out 和关联台人工确认语义混在一起。本地 Browser smoke 只证明页面 fresh contract 和 UI 反馈，不替代真实 worker drain。
- 文档影响：更新 `e2e-coverage.md`、`tests.md`、`docs/dev/testing.md`、`docs/dev/spec-first-e2e-inventory.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：`web/e2e/imports-invoices-flow.spec.ts` 的 downstream fresh test 在确认导入后依次打开销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计，断言对应 API `read_model_status=fresh` 且页面展示导入影响行；同时 strict browser error capture 增加非预期 5xx response 捕获。
- 验证命令：`cd web && npx playwright test e2e/imports-invoices-flow.spec.ts --project=chromium` 通过 6 tests。
- 未测风险：真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain、真实发票大文件、真实信息汇总表浏览器上传、search 外层 UI、真实下游大表和导出下载仍需后续 real-infra/nightly 或 staging smoke。
- 后续事项：下一轮优先补真实基础设施 worker drain smoke，或补信息汇总表真实样本/超大文件/上传中断。

## 2026-06-19 - 发票导入 Spec-first Browser 负面路径

- 目标：把 `/imports/invoices` 从单一 happy path Browser smoke 提升为 Spec-first E2E 基线，覆盖重复明细、`preview_stale` 和 confirm failure，防止页面在导入失败或预览过期时仍显示成功或刷新下游。
- 影响范围：deterministic Playwright mock、`web/e2e/imports-invoices-flow.spec.ts`、发票导入模块 Spec-first E2E 文档和全局测试闭环状态。
- 关键决策：不改产品逻辑；复用共享导入工作流和现有 API mapper 的 `preview_stale` 文案，只在 mock 中增加发票导入专用失败开关。mock confirm 成功不等同于真实 worker drain，真实 PostgreSQL/RabbitMQ/Redis/systemd worker 和下游 read model freshness 仍作为 `external-risk` 记录。
- 文档影响：新增 `e2e-spec.md`、`e2e-coverage.md`，更新 `README.md`、`tests.md`、全局 Spec-first inventory、测试说明和闭环状态。
- 测试覆盖：Browser E2E 覆盖真实 file input、每文件进/销项方向、preview audit、重复项明细、confirm 成功等待显式 targets 且零 Workbench 页面请求、`preview_stale`/confirm 500 无 success 且零 barrier；组件测试覆盖 targets 为空时直接完成且零 Workbench 请求。
- 验证命令：见本轮最终交付说明。
- 未测风险：真实发票 Excel、大文件、真实 import worker drain、derived lifecycle worker、下游 pending invoices/tax/input-output/OA/cost/search read model 最终 fresh 仍需 staging 或生产只读 smoke。
- 后续事项：继续补真实基础设施 worker drain smoke，或补发票导入后的下游多页面 Browser fan-out。

## 2026-06-19 - 发票导入后台链路闭环

- 目标：修复发票文件上传/预览/确认后，用户看到导入成功但关联台仍长期刷新中的闭环缺口。
- 影响范围：发票导入确认后的 background job、`import.fact.changed` durable event、下游 workbench/workbench_relation/tax/cost/invoice lifecycle/search read model refresh，以及 App Status 导入进度展示。
- 关键决策：发票导入成功的用户口径必须同时满足三段链路：文件导入 job 完成、`import.fact.changed` 被 import worker claim/ack、下游 read model dirty scope 被各自 worker 刷新并通过 freshness/readiness 暴露。RabbitMQ 模式下 `import.fact.changed` 不得只注册在 PostgreSQL claim override；它必须进入 import worker 的统一 claim event types 和 RabbitMQ dispatch route。
- 文档影响：同步 runtime worker、关联台和系统状态模块实施记录；发票导入 API contract 与业务字段不变。
- 测试覆盖：`tests/test_import_job_queue.py` 覆盖 RabbitMQ import worker check 暴露 `import.fact.changed` route；`tests/test_runtime_worker_registry.py` 覆盖 import worker 所有 transport claim event types；`web/src/test/AppStatusIndicator.test.tsx` 覆盖发票导入进度在全局状态框显示为“正在导入发票 210/500”。
- 验证命令：见本轮最终交付说明。
- 未测风险：本地测试不执行真实 RabbitMQ broker/systemd 长跑，也不证明生产历史 pending 自动 drain；发布后需只读观察 backlog 并重新导入小批量发票 smoke。
- 后续事项：重新导入验证前，只能清理本次导入批次对应发票/source links/import rows，不能删除历史发票事实；清理前必须用 import session/batch/job 精确圈定范围。

## 2026-06-18 - 服务器发票预览 500 修复

- 目标：修复服务器 `/imports/files/preview` 在发票 Excel 预览完成后返回 `接口处理失败` 的问题。
- 影响范围：发票导入预览后的 PostgreSQL import facts 持久化、`job.outbox_events` 的 import-fact changed 入队、下游 read model dirty/outbox fan-out。
- 关键决策：不改 Excel 解析和模板识别；真实异常来自 `PostgresCoreRepository._mark_import_fact_read_models_dirty()` 中 `job.outbox_events` 的 `ON CONFLICT` predicate 仍使用旧合同 `status in ('pending', 'processing')`，而当前 `0016` 后的 `outbox_events_dedupe_uidx` 只覆盖 `status = 'pending'`。修复为与 schema 一致的 predicate。
- 文档影响：更新本实施记录和 `tests.md`；API contract 和业务状态不变。
- 测试覆盖：新增 `tests/test_postgres_repositories_core.py::test_save_imports_marks_read_models_dirty_and_outbox_event` 断言 import fact outbox 使用 `status = 'pending'`，并用用户提供的 5 个真实 Excel 在本地一次性 PostgreSQL schema 中跑 `/imports/files/preview` smoke。
- 验证命令：本地 PostgreSQL 临时库 `fin_ops_preview_test_260618` 完整迁移后，通过同一 HTTP handler 上传 5 个真实 Excel，返回 `status=200`、session `preview_ready`、391 行、错误 0，并写入 `app.import_batches=5`、`app.import_batch_rows=391`、`app.import_files=5`、`app.file_objects=5`、`job.outbox_events(import.fact.changed)=14`。
- 未测风险：尚未在服务器用真实 OA 登录态重新点击页面确认；当前 SSH 用户不能读取 `fin-ops.service` journal traceback，生产验证需要发布本修复后再看 `/health/ready.api_performance["POST /imports/files/preview"].last_status_code` 和页面上传结果。
- 后续事项：发布后如果仍报错，优先查看服务器 journal 中新的 traceback；不要再按模板识别方向排查。

## 2026-06-18 - 发票信息汇总表模板识别

- 目标：支持用户从发票平台导出的 `信息汇总表` Excel，该格式使用 `数电号码`、`购方企业名称`、`购方税号`、`销方企业名称`、`销方税号`、`商品名称` 等表头，旧导入器会因缺少 `购买方名称` / `销方识别号` 判定为无法识别模板。
- 影响范围：`FileImportService` 发票模板识别、发票行解析、file/session preview、发票导入测试矩阵。
- 关键决策：不新增前端 API 或独立 batch type；在 `invoice_export` 模板内做发票表头别名归一，保持 normalized row、重复审计、confirm 和下游 lifecycle 语义不变。`信息汇总表` 末尾 `份数：...金额：...` 汇总页脚不是发票明细，解析阶段跳过。
- 文档影响：更新本实施记录和 `tests.md` 的场景覆盖、历史 bug 回归和 smoke flow；长期 API contract 不变。
- 测试覆盖：新增 `test_preview_accepts_invoice_summary_header_aliases` 和 `test_preview_detects_invoice_summary_without_template_override`，覆盖表头别名、前端 override 场景、自动识别场景和汇总页脚跳过。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service tests.test_import_file_api tests.test_import_api tests.test_import_service tests.test_import_preview_audit -v`；本地还用用户提供的 5 个真实 Excel 跑 `FileImportService.preview_files` smoke，结果均为 `preview_ready` 且 `errors=0`。
- 未测风险：尚未通过真实浏览器上传和真实 background worker drain 确认完整 confirm -> lifecycle -> 下游 read model 链路；真实业务文件不纳入仓库 fixture。
- 后续事项：如发票平台继续新增表头口径，优先扩展 alias mapping 并补合成 fixture，不保存真实业务 Excel。

## 2026-06-19 - 发票导入真实 write-flow SLO audit profile

- 目标：补齐发票导入 Spec-first E2E 闭环中的真实 read model/worker 证据入口，避免只用 deterministic Browser mock 或直接 enqueue smoke 声称真实写链路已闭环。
- 影响范围：`write_operation_slo_audit`、发票导入测试矩阵、`IMPORT-INVOICE-E2E-009` 真实基础设施 gate。
- 关键决策：profile 名使用业务规格 `invoice_import_confirmed`，但匹配真实 durable queue reason：发票文件确认后的大多数下游 read model refresh 使用 `import_state_changed`，税金抵扣使用 `invoice_file_import_confirm`。
- 覆盖 scope：Workbench、Workbench relation、invoice lifecycle、search、待找发票、进项使用、销项收款、OA 待付款、成本统计和税金抵扣。
- 测试覆盖：新增 `tests/test_write_operation_slo_audit.py` 回归，验证完整 scope 才通过，缺少成本统计等下游 scope 时必须失败。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_write_operation_slo_audit -v`；`bash scripts/verify.sh docs`；`bash scripts/verify.sh infra-smoke`。
- 未测风险：本地契约测试不产生真实发票确认 outbox rows；仍需 staging/发布前运行 `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit --json --operation invoice_import_confirmed --lookback-hours 24`，并配合真实 import worker / read model worker drain 观察。

## 2026-06-16 - 发票导入合成大重复组守护

- 目标：为 P2/P3 发票大文件和超大重复组风险补本地可重复证据，防止同文件重复发票在 preview audit 中被全部当作可确认。
- 影响范围：`FileImportService.preview_files`、invoice Excel parser、invoice identity、import preview duplicate audit、发票导入测试矩阵。
- 关键决策：不改导入行为；使用 240 行合成发票 Excel fixture 锁定当前 contract：同一稳定 identity 只产生一个 confirmable representative，其余 239 行进入 duplicate group 和 skipped count。
- 文档影响：更新 `tests.md` 的场景覆盖、历史 bug 回归和未测风险；P2/P3 台账记录为 local synthetic evidence。
- 测试覆盖：新增 `test_preview_bounds_large_invoice_duplicate_group_to_one_confirmable_row`。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_service.ImportFileServiceTests.test_preview_bounds_large_invoice_duplicate_group_to_one_confirmable_row -v`；本轮也与银行/ETC 合成导入测试一起运行通过。
- 未测风险：真实客户发票大文件、历史模板变体、异常编码、真实浏览器上传耗时、真实 worker drain 和下游页面 fresh 仍需 staging/manual smoke。
- 后续事项：拿到用户批准的真实发票样本后，在 staging 跑文件 preview/confirm/job/read-model smoke，不在仓库保存真实业务文件。

## 2026-06-16 - 发票导入 App Status job domain 闭环

- 目标：关闭发票文件确认后 App Status/job feedback 可能落到泛化导入域的缺口，让用户能从全局状态返回 `/imports/invoices`。
- 影响范围：`/imports/files/confirm` 的 `file_import` background job source、`app_status_job_registry` 的共享 import fallback、发票导入模块测试矩阵和状态机。
- 关键决策：具体文件确认 job 使用 `source.affected_domains` / `source.route` 精确报告发票导入页；共享 `import.process.requested` 仍保留多导入域兜底，避免在没有文件类型上下文时伪装成单一页面。
- 文档影响：更新 `README.md`、`state-machine.md`、`tests.md`，并在 Phase16 GSD 产物记录本次闭环。
- 测试覆盖：新增/更新 API contract 与 App Status registry 回归，覆盖发票确认 job domain/route 和泛化 import fallback。
- 验证命令：`PYTHONPATH=backend/src python3 -m unittest tests.test_import_file_api.ImportFileApiTests.test_confirm_files_imports_only_selected_files_from_session`；扩展后端 187 tests；前端导入页/App Status 27 tests；`bash scripts/verify.sh docs`。
- 未测风险：真实大文件、真实 Postgres/RabbitMQ/Redis/systemd worker drain、worker crash/retry、下游真实浏览器大数据和导出 smoke。
- 后续事项：进入 `imports-etc-invoices` phase，确认 ETC 导入 job domain/route 与本页一致闭环。

## 2026-06-11 - 发票导入测试闭环首轮

- 目标：补齐 `/imports/invoices` 的影响面、七类测试矩阵、状态机、历史 bug 回归库和验证命令。
- 影响范围：共享 import workflow、file/session import API、发票 normalizer、import worker、`invoice_import_confirmed` derived lifecycle、关联台、待找发票、税金抵扣、进项/销项/OA 待付款、成本统计、搜索和 App Status。
- 关键决策：不新增低价值测试；先把现有发票导入和下游回归测试登记到模块矩阵，并把真实基础设施/大样本风险标记为 `documented-risk`。
- 文档影响：更新 `README.md`、`tests.md`、`state-machine.md`、`docs/dev/testing-closure-dependency-map.md` 和 `docs/dev/testing-closure-state.md`。
- 测试覆盖：覆盖七类测试；重点保护发票 identity、重复审计、preview stale、file confirm、worker/job、derived lifecycle、下游 read model/API 和前端交互状态。
- 验证命令：见 `tests.md` 和 `docs/dev/testing-closure-state.md` 最近验证命令。
- 未测风险：真实发票大文件/历史模板、真实 Postgres/RabbitMQ/Redis/systemd worker drain、worker crash/retry、下游真实浏览器大数据和导出 smoke。
- 后续事项：后续模块处理 `imports-etc-invoices`；另行专项校准共享 `import.process.requested` App Status affected domain。
## 2026-07-15 税局导出明细行整票化

- 根因：税局导出是一票多行，旧 parser 将每一物理行作为独立 invoice import row；首行创建 canonical invoice，后续明细成为 duplicate，造成 9 张发票合计缺少 15 条明细/折扣金额。
- 决策：同文件按发票强身份聚合不同明细；完全相同重复行保留，部分重复冲突 fail closed。历史严格合同 Audit 与受控 repair 使用同一聚合规则。
## 2026-07-22 - 精确导入生命周期生产修复边界

- 目标：在根因修复发布后，安全恢复已被旧 stale preview writer 降级的历史 batch/file 状态，不修改 canonical 发票、导入行、job 或 read model。
- 设计：复用既有 `import-audit-repair`，增加必须成对出现的 `--batch-id` / `--file-id`；dry-run 是 repeatable-read read-only，execute 是 serializable + advisory lock + expected fingerprint。纯 plan 只接受唯一 succeeded job、完整 batch counter/row decision、created invoice owner 和成功行 `manual_invoice_import` source-link 闭环。
- 写入范围：只把精确目标从 `batch pending + file preview_ready + batch_id null` 恢复为 `batch completed + file confirmed + batch_id/session_status terminal`；SQL 自带旧状态与 preview batch precondition，任一步 rowcount 不是 1 都回滚整个事务。
- 非目标：不新增 HTTP 修复接口，不做常驻扫描，不重放 worker/read model，不覆盖 raw payload 的其它字段，不支持其它中间态推断。
- 测试：`tests/test_import_audit_repair_ops.py` 覆盖 plan、幂等、fail-closed、CLI exact target 与 repository precondition；`tests/test_app_postgres_mode_integration.py` 覆盖真实 PostgreSQL 状态恢复（无测试 DSN 时 skip）。
