# 发票导入测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| 页面入口 | `web/src/pages/imports/ImportInvoicesPage.tsx` | 只传 `mode="invoice"`，共享工作流改动会同时影响银行流水和 ETC 导入 |
| 共享工作流 | `web/src/components/imports/ImportWorkflowPage.tsx`、`ManualInvoiceEntryDrawer.tsx` | 每文件票据方向、单张人工录入、可选 OCR、preview stale、重复审计、fresh entry、当前 preview discard、route unmount cleanup、job feedback、read-only 导入门禁 |
| 补充凭证只读画廊 | `SupportingDocumentGalleryDrawer.tsx`、`features/workbench/api.ts` | 入口只在 invoice mode；打开前零请求、9 条 cursor page、日期分组、3/2/1 列、图片/PDF同抽屉预览、只读用户可见且无 mutation |
| Browser e2e | `web/e2e/imports-invoices-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 真实 Chromium 覆盖文件、方向、预览、确认、错误与权限；确认后打开各下游页面验证 canonical 结果，并证明单独发票导入不会形成 OA 项目成本。 |
| 前端 API mapper | `web/src/features/imports/api.ts` | multipart `file_overrides`、`batch_type`、snake_case/camelCase、`preview_stale` 错误映射、job/session shape |
| HTTP routes | `server.py` `/imports/files/preview`、`/imports/invoices/manual/recognize`、`/imports/invoices/manual/preview`、`/imports/files/confirm`、`/imports/files/retry`、`/imports/files/sessions/{session_id}` | manual recognize 只读预填；所有正式写入仍收敛到 file/session confirm；confirm 必须防 stale、unknown selected ids 和重复提交 |
| File import service | `FileImportService` | 损坏 Excel file-level error、模板识别、session/file/batch id、selected files confirm、预览审计 |
| Normalization core | `ImportNormalizationService` | input/output invoice identity、digital invoice number fallback、重复/疑似重复、已存在 ETC-linked canonical invoice 合并、submitted ETC metadata 反向链接、source links、tags |
| Import processing | `ImportProcessingService` | file confirm job 后必须执行发票生命周期、共享 relation/matching exact-scope 计算和 state persistence；不得生成 Workbench page scope |
| Derived lifecycle | `DerivedDataLifecycleService` | `invoice_import_confirmed` 必须先刷新 `invoice_lifecycle`，再影响待找发票、税金、进项/销项/OA 待付款、成本、搜索 |
| Read model / worker | `runtime_worker_handlers.py`、runtime queue、App Status registries、`write_operation_slo_audit` | import job 成功不等于登记的下游 consumer 已收敛；worker/readiness 失败必须在 App Status 暴露；真实发票确认后应能审计 `workbench_relation`/matching 与下游 direct-canonical 页面状态，且 Workbench page、Search/no-OA event 为零 |

## 场景覆盖清单

- 发票导入页必须发送每文件方向：`input_invoice` / `output_invoice`。
- 单张人工录入必须覆盖纯手工、JPG/JPEG/PNG/PDF 点击或拖拽识别、OCR 后可编辑、20 位票号代码可选、传统票代码必填、0–100 数字税率、红字正数输入转 canonical 负数、金额平衡、精确重复阻断、返回编辑 discard 和普通 confirm job。
- Browser e2e 必须覆盖发票导入页真实选择控件、预览按钮禁用/启用、慢预览 in-flight 动作锁定、审计汇总、重复项明细、未导入项明细、确认导入、显式 operation barrier 等待和零 Workbench 页面请求。
- 未获发票导入页授权的用户不能打开页面、选择文件、预览或确认导入；获权用户可执行完整导入流程。
- 补充凭证画廊仍按自身业务状态控制上传/删除；关闭、重开和分页请求必须 abort/latest-wins，不能刷新导入主体或污染其它导入模式。
- 预览必须显示重复审计 counts、duplicate groups 和 review copy。
- 每次进入或重新激活页面必须从空白本地草稿开始，不读取 sessionStorage，不请求服务端活跃 session 列表；离开后才返回的 preview 结果必须丢弃。
- `preview_stale` 必须映射为重新预览提示，不能继续确认旧结果，不能展示“已确认导入”，不能调用 operation barrier 或 Workbench 页面 API。
- stale gate 必须逐行比较 decision、linked object type/id；duplicate/importable 汇总不变但 canonical invoice owner 调换时仍必须拒绝确认。
- `suspected_duplicate` preview 可显示候选 invoice，但 confirm 后 terminal row 必须清空该非权威 link；created、status_updated、duplicate_skipped 的正式引用不能被清空。
- confirm API/worker 入队失败必须错误可见，不能展示“已确认导入”，不能调用 operation barrier 或 Workbench 页面 API。
- 损坏 Excel 必须是 file-level `unrecognized_template`，不能让整个 preview 请求崩溃。
- 含唯一 `发票基础信息` 的税务平台多 sheet 工作簿必须直接以其生成 canonical 发票，前置 `信息汇总表` 只能作为明细证据；表头畸形、重名或明细身份错配必须整文件 fail closed，不能回退首个可解析 sheet。没有该 sheet 的历史单 sheet `信息汇总表` 仍识别既有表头别名并跳过汇总页脚。
- 服务器 PostgreSQL runtime 下，发票 preview/full snapshot persistence 不得直接写 import fact dirty/outbox 旁路；确认后的刷新必须通过 import processing、derived lifecycle 和 read model gateway 边界收敛。
- 发票 preview/confirm 必须对本批次 invoice identity 做批量 preload，不能对每行逐次远程 DB 查重；preview 只保存预览/session 状态，不能触发 workbench/read model 刷新或保存 `workbench_pair_relations` 快照。
- preview/retry 只能持久化当前 session 与其 preview batches；另一个进程完成 confirm 后，持有 stale 内存的 API 再预览银行文件也不得把已完成发票降级。PostgreSQL batch 与 file/session delta 必须同事务回滚。
- 240 行合成发票同文件重复组必须只产生一个 confirmable representative，其余进入 duplicate audit / skipped count。
- input/output invoice identity 必须覆盖稳定号码、占位电子发票号、弱 fingerprint、跨批次重复、批内重复。
- ETC 来源或 tag 指向 ETC 时，input invoice import 只允许合并已存在 canonical invoice，不能因为 ETC metadata/ZIP 来源创建新的统一发票池事实。
- 正式进项发票晚于历史 submitted/manual-submitted ETC 批次导入时，必须按强身份把 ETC metadata 反向链接到同一 canonical invoice，并幂等写入 `app.etc_batch_invoice_links`；严格匹配失败时不得自动隐藏或合并。
- confirm 必须跳过重复行、更新 source status、持久化 source links，并对 later preview batch 的重复保持幂等。
- `invoice_import_confirmed` 必须推进 canonical invoice/source-link versions，并保持 Workbench relation/matching 的独立 owner 合同；不得 enqueue Workbench page、Search 或其它已退休页面 projection。
- input-only、output-only 与混合导入必须只改变对应方向的 canonical 发票事实；进项使用、销项收款和其它 direct 页面在下一次 normal GET 中按自身查询读取。
- 不能把导入确认返回当作所有页面已经完成重读；Browser/E2E 必须明确打开受影响页面并验证 canonical 结果，而不是等待已退休 freshness。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_import_service.py`、`tests/test_import_preview_audit.py`、`tests/test_manual_invoice_entry_service.py`、`tests/test_invoice_header_fact_repair_service.py` | 覆盖发票 identity、人工录入红蓝字/金额/税率/代码条件/重复、批内/跨批重复、source links，以及 11 张精确表头事实修复。 |
| 2. Service-layer tests | 适用 | `tests/test_import_file_service.py`、`tests/test_import_job_queue.py`、`tests/test_import_formalization_api.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_import_audit_repair_ops.py`、`tests/test_postgres_repositories_core.py` | 覆盖 file/session preview/confirm、stale preview、header/detail sheet I/O、job queue、retry/original file retention、derived lifecycle fan-out，以及修复 dry-run/CAS/队列刷新。 |
| 3. API contract tests | 适用 | `tests/test_import_api.py`、`tests/test_import_file_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_tax_offset_api.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_output_invoice_collection_api.py` | 覆盖 import API shape、`batch_type`、`preview_stale`、job payload、read-model 下游状态字段，以及税金抵扣 canonical snapshot token/无旧状态字段。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_import_job_queue.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_write_operation_slo_audit.py` | 覆盖 import worker、invoice lifecycle 顺序、仍存在的 read-model 下游 App Status/readiness，并用 `invoice_import_confirmed` write-operation profile保护共享下游；税金抵扣页面读取不再属于本类。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/ImportCenterPage.test.tsx`、`web/src/test/ManualInvoiceEntryDrawer.test.tsx`、`web/src/test/SupportingDocumentGalleryDrawer.test.tsx`、`web/src/test/WorkbenchApi.test.ts`、`web/src/test/ImportsApi.test.ts`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/imports-invoices-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 覆盖每文件方向、人工录入、补充凭证惰性分页/预览/只读权限、预览审计、错误提示、fresh entry、显式清空/discard、延迟响应隔离、API mapper 和既有浏览器导入回归。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_workbench_v2_api.py`、`tests/test_tax_offset_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-invoices-flow.spec.ts` | 覆盖 import confirm -> stale preview protection -> Workbench 与其它 direct-canonical 下游 normal GET；前端导入流程不主动请求 Workbench 页面，用户进入关联台时直接读取已提交事实。真实 import/matching worker drain 仍需 staging/后续 smoke。 |
| 7. Existing feature regression tests | 适用 | 上述全部，以及下游模块测试矩阵、`web/e2e/imports-invoices-flow.spec.ts` | 每次改 shared import、invoice fact、lifecycle、read model 或 App Status 时，都必须回归发票导入和下游页面旧行为。 |

## 历史 bug 回归库

| 风险 | 保护测试 |
| --- | --- |
| 占位电子发票号遮蔽稳定 code+number key | `tests/test_import_service.py::ImportNormalizationServiceTests::test_invoice_placeholder_digital_number_does_not_mask_stable_code_number_key` |
| 相同数字发票号没有被归入重复组 | `tests/test_import_preview_audit.py::ImportPreviewAuditTests::test_same_digital_invoice_number_is_grouped_as_duplicate` |
| 弱 fingerprint 被误用导致不同发票合并 | `tests/test_import_service.py::ImportNormalizationServiceTests::test_upsert_etc_invoice_does_not_reuse_weak_fingerprint_when_invoice_number_changed` |
| 既有 canonical invoice 读取时保留过期弱 fingerprint | `tests/test_import_service.py::ImportNormalizationServiceTests::test_existing_canonical_invoice_drops_weak_fingerprint_on_load` |
| 历史 ETC-linked canonical invoice 与 input invoice import 重复 | `tests/test_import_service.py::ImportNormalizationServiceTests::test_input_invoice_import_merges_existing_etc_canonical_invoice_without_duplicate` |
| 历史 submitted ETC 批次先存在，正式进项发票后导入导致关联台重复散票 | `tests/test_import_service.py::ImportNormalizationServiceTests::test_input_invoice_import_links_existing_submitted_etc_metadata_when_formal_invoice_arrives_later`、`tests/test_etc_batch_invoice_link_service.py`、`tests/test_postgres_repositories_core.py::test_find_submitted_etc_invoice_by_identity_returns_active_batch_metadata`、`tests/test_postgres_repositories_core.py::test_upsert_etc_batch_invoice_link_is_idempotent_by_batch_identity`、`tests/test_workbench_query_postgres_integration.py::WorkbenchQueryPostgresIntegrationTests::test_page_etc_hydration_is_one_statement_and_matches_legacy_dto`、`tests/test_repair_submitted_etc_invoice_overlaps_tool.py` |
| 预览后源事实变化仍允许确认 | `tests/test_import_file_service.py::ImportFileServiceTests::test_confirm_session_rejects_stale_preview_when_existing_records_change`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_import_file_confirm_returns_preview_stale_when_existing_records_change` |
| 大重复组被全部当作可确认行 | `tests/test_import_file_service.py::ImportFileServiceTests::test_preview_bounds_large_invoice_duplicate_group_to_one_confirmable_row` |
| 发票导入路由重挂载恢复历史预览，或延迟响应污染 fresh 页面 | `web/src/test/ImportCenterPage.test.tsx` 中 fresh entry / late preview response 回归 |
| 发票慢预览期间用户重复触发 preview、清空或确认造成重复请求/半写状态 | `web/e2e/imports-invoices-flow.spec.ts` 的 slow preview Browser 回归，断言预览/清空/确认动作锁定且只提交一次 preview |
| 损坏发票文件导致整个 preview 崩溃，或 confirm 误提交不可导入文件 | `web/e2e/imports-invoices-flow.spec.ts` 的 corrupt mixed Browser 回归，断言 file-level error、未导入项明细和 `selected_file_ids` 只包含正常文件 |
| 发票导入后成本统计伪造项目成本 | `web/e2e/imports-invoices-flow.spec.ts` 断言 direct-canonical 成功，但“按项目”不存在仅由发票导入生成的成本。 |
| 发票导入确认或下游 fresh 成功后页面仍残留导入失败/read model 失败提示 | `web/e2e/imports-invoices-flow.spec.ts` 的 success visible-error guard，断言导入页和六个下游成功节点没有导入失败、后台导入失败或 read model 失败等可见错误残留 |
| 发票导入 `preview_stale` 仍显示成功或触发后续探测 | `web/e2e/imports-invoices-flow.spec.ts` 的 preview stale Browser 回归，断言错误可见、无 success、零 operation barrier、零 Workbench 页面请求 |
| 发票导入 confirm 失败后显示成功或触发后续探测 | `web/e2e/imports-invoices-flow.spec.ts` 的 confirm failure Browser 回归，断言错误可见、无 success、零 operation barrier、零 Workbench 页面请求 |
| 发票导入后 relation/matching 队列长期同步中 | `tests/test_runtime_queue.py::RuntimeQueueRepositoryTests::test_defer_event_does_not_let_older_done_event_cover_newer_processing_event`、`tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot`、`tests/test_import_processing_service.py::test_file_import_confirm_job_returns_import_write_targets`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_import_fact_changed_handler_completes_matching_dirty_scope`、`tests/test_import_job_queue.py::ImportJobRepositoryTests::test_invoice_relation_scope_helpers_split_input_and_output_file_months`、`tests/test_read_model_scope_contract.py`、`tests/test_read_model_slo_smoke.py`；关联台页面没有 import invalidation/refresh 队列，normal GET 直接读取已提交 canonical facts。 |
| 发票导入 preview/confirm 因逐行 DB 查重和 preview 重型持久化变慢 | `tests/test_import_service.py::ImportNormalizationServiceTests::test_preview_import_preloads_invoice_identity_in_bulk`、`tests/test_import_service.py::ImportNormalizationServiceTests::test_confirm_import_refreshes_invoice_identity_in_bulk`、`tests/test_postgres_repositories_core.py::test_find_invoices_by_identity_keys_uses_single_bulk_lookup`、`tests/test_import_file_api.py::ImportFileApiTests::test_preview_files_uses_lightweight_import_preview_persistence` |
| 发票文件确认 background job 在 App Status 中落到泛化导入域 | `tests/test_import_file_api.py::ImportFileApiTests::test_confirm_files_imports_only_selected_files_from_session` 断言 `affected_domains=["imports_invoices"]`、route `/imports/invoices`；`tests/test_app_status_overview_service.py` 覆盖泛化 import fallback |
| 发票 `信息汇总表` 表头别名不被识别，或汇总页脚被当作错误发票行 | `tests/test_import_file_service.py::ImportFileServiceTests::test_preview_accepts_invoice_summary_header_aliases`、`tests/test_import_file_service.py::ImportFileServiceTests::test_preview_detects_invoice_summary_without_template_override` |
| 多 sheet 导出成功解析首个 `信息汇总表` 后提前返回，导致 canonical 只取第一条商品明细 | `tests/test_import_file_service.py` 的 authoritative header、malformed header fail-closed、detail identity mismatch 回归；`tests/test_invoice_header_fact_repair_service.py` 与 `tests/test_import_audit_repair_ops.py` 保护 11 张存量修复的精确性、幂等和恢复清单 |
| 服务器预览完成后 PostgreSQL import-fact outbox 旁路导致刷新风暴 | `tests/test_postgres_repositories_core.py::test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot` 断言 full snapshot persistence 不再直接写 `job.read_model_dirty_scopes` / `job.outbox_events`；正式刷新必须走 import processing、derived lifecycle 和 read model gateway 边界 |
| stale API 后续预览把已完成发票状态覆盖回 pending | `tests/test_import_file_service.py::ImportFileServiceTests::test_preview_session_persistence_payload_excludes_unrelated_sessions_and_canonical_facts`、`tests/test_import_formalization_api.py::ImportFormalizationApiTests::test_stale_api_preview_cannot_downgrade_another_process_confirmed_import`、`tests/test_postgres_repositories_core.py::test_save_import_delta_rolls_back_batch_when_file_write_fails`、`tests/test_read_model_architecture_guards.py` |
| 放弃 preview 后 batch canonical status 为 `reverted`、formal payload 仍为 `pending`，导致系统页面 Audit 阻断发布 | `tests/test_import_lifecycle_service.py::ImportLifecycleServiceTests::test_postgres_discard_is_atomic_owned_and_rejects_active_job`、`tests/test_audit_invoice_import_page.py::InvoiceImportPageAuditTests::test_formally_reverted_preview_batch_is_not_reported_as_invalid`、`tests/test_import_audit_repair_ops.py` 的 reverted batch plan/idempotency/fail-closed/repository/CLI 测试 |

## 关键 smoke flows

- 发票 Excel 上传 -> 每文件选择进项/销项 -> 预览 -> 确认 -> import worker/job 完成 -> invoice lifecycle -> 待找发票、税金抵扣及命中方向页面；成本统计访问可重读 canonical facts，但没有完成 OA 与付款流水关系时不得产生项目成本。
- Staging write-flow audit：真实发票确认后运行 `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit --json --operation invoice_import_confirmed --lookback-hours 24`，必须看到两个保留 read model 的 scope 与 direct-canonical 下游检查通过，并确认已退休 Search/no-OA event 为零。
- Runtime queue drain smoke：真实发票确认后只读核对本次导入时间窗内 `job.outbox_events` 不存在 stuck `processing/pending/dead-lettered`，`job.read_model_dirty_scopes` 中本次发票导入涉及的 `import_state_changed` / `invoice_file_import_confirm` scope 均已 `done`；发票导入不应新增 `import_facts_changed` 旁路，且 pending invoice 使用 `:<YYYY-MM>` 月级 scope 而不是仅有 `expense:all/income:all` 全量 aggregate。
- 标准多 sheet 发票 Excel 上传 -> 唯一 `发票基础信息` 生成一票一行 canonical preview -> `信息汇总表` 附着明细证据 -> 选择进项/销项 -> 重复审计和确认；历史单 sheet `信息汇总表` 继续走既有聚合合同。
- 真实 PostgreSQL runtime smoke：5 个真实发票 Excel 上传 -> preview 返回 200 -> `preview_ready` 391 行 -> `app.import_batches`、`app.import_batch_rows`、`app.import_files` 和 `app.file_objects` 均成功写入；确认后通过真实 `*.read_model.refresh` 而不是 `import.fact.changed` 旁路收敛。
- Browser e2e smoke：两份发票 XLSX 上传 -> 分别选择销项/进项 -> 预览 audit/重复明细/需复核文案 -> 确认导入 -> 等待响应声明的 operation barrier targets -> 草稿清空 -> 零 Workbench 页面请求 -> 无错误残留。
- Browser downstream smoke：发票导入确认 -> 打开下游页面 -> 税金抵扣/成本统计 direct-canonical GET 返回 `200` 且无旧状态字段 -> 成本统计“按项目”不存在仅由本次发票导入生成的成本 -> 无可见错误残留。
- Browser slow-preview smoke：两份发票 XLSX 上传 -> 分别选择销项/进项 -> preview request in-flight -> 预览/清空/确认按钮禁用 -> 请求完成后恢复，且只提交一次 preview。
- Browser corrupt-file smoke：损坏发票文件 + 正常发票文件混合上传 -> 损坏文件作为 file-level error 进入未导入项 -> confirm 只提交正常文件 ID -> 等待显式 operation barrier targets，零 Workbench 页面请求。
- Browser negative smoke：两份发票 XLSX 上传 -> 预览 -> confirm 返回 `preview_stale` 或 500 -> 错误可见 -> 无“已确认导入” -> 零 operation barrier、零 Workbench 页面请求。
- 240 行同文件重复发票 -> preview audit 只保留一个 confirmable representative -> duplicate group 展示 240 行，skipped count 为 239。
- 预览后手工导入或另一个导入批次改变发票事实 -> 当前 confirm 返回 `preview_stale` -> 前端要求重新预览。
- 发票导入确认 -> canonical 发票可见 -> matching 按独立合同处理；关联台下一次 direct GET 重新计算，不使用旧 cache 或 page invalidation。
- input invoice import 与历史 ETC-linked canonical invoice 或 submitted ETC metadata 相遇 -> 严格匹配时只更新同一 canonical invoice、保留 ETC tag 并从关联台普通 open 发票视图隐藏；ETC ZIP 本身不得创建新的 canonical invoice。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_import_api \
  tests.test_import_service \
  tests.test_import_file_service \
  tests.test_import_file_api \
  tests.test_manual_invoice_entry_service \
  tests.test_import_preview_audit \
  tests.test_import_job_queue \
  tests.test_import_formalization_api \
  tests.test_derived_data_lifecycle_service \
  tests.test_invoice_lifecycle_page_integration \
  tests.test_tax_offset_api \
  tests.test_input_invoice_usage_api \
  tests.test_oa_pending_payment_api \
  tests.test_output_invoice_collection_api \
  tests.test_write_operation_slo_audit \
  tests.test_runtime_worker_registry \
  tests.test_app_status_overview_service \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_import_file_confirm_returns_preview_stale_when_existing_records_change \
  tests.test_workbench_query_postgres_integration.WorkbenchQueryPostgresIntegrationTests.test_direct_initial_and_groups_use_canonical_facts_without_read_model \
  tests.test_read_model_scope_contract \
  -v

pytest -q \
  tests/test_import_service.py \
  tests/test_postgres_repositories_core.py \
  tests/test_import_file_api.py \
  tests/test_import_processing_service.py

cd web && npm test -- --run \
  src/test/ImportsApi.test.ts \
  src/test/ManualInvoiceEntryDrawer.test.tsx \
  src/test/ImportCenterPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx

cd web && npx playwright test e2e/imports-invoices-flow.spec.ts
cd web && npx playwright test e2e/permissions-role-matrix.spec.ts

bash scripts/verify.sh docs
```

真实 staging/发布前 worker/read model 验证：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --json \
  --operation invoice_import_confirmed \
  --lookback-hours 24
```

该命令审计真实 durable queue 中最近发票文件确认写链路产生的 `*.read_model.refresh` 事件；它不替代 Playwright 的用户流程，也不替代 `read_model_slo_smoke --apply` 的直接 enqueue-to-fresh worker drain。

## Nightly CI 覆盖

`scripts/verify.sh all` 会运行后端 `unittest discover`、前端 Vitest、build、deterministic Playwright smoke 和 docs check，因此 nightly CI 会覆盖本模块现有自动化测试、`web/e2e/imports-invoices-flow.spec.ts` 的导入成功/下游 fresh/成功后无错误残留，以及 `web/e2e/permissions-role-matrix.spec.ts` 的共享导入 read-only 门禁。真实大文件、真实 Postgres/RabbitMQ/Redis/systemd worker drain 仍需 staging 或发布前 smoke。

## 未测风险

- 本地已覆盖 240 行合成发票重复组；真实客户发票 Excel 大文件、历史模板变体、异常编码、超大重复组内存/耗时和真实浏览器上传仍需 staging/manual smoke。
- 真实 Postgres/RabbitMQ/Redis/systemd import worker drain、worker crash/retry、RabbitMQ transport wakeup 未由本地单测完全证明；`write_operation_slo_audit --operation invoice_import_confirmed` 已有本地契约测试，但仍需要 staging 中真实发票确认样本产生 recent outbox rows 才能证明真实 write-flow。
- Browser e2e 当前覆盖 deterministic mock 下的发票上传、方向选择、预览审计、慢预览动作锁定、损坏文件混合、确认、显式 operation barrier 等待和零 Workbench 页面请求，以及销项收款/进项使用/待找发票/OA 待付款、税金抵扣/成本统计的下游展示；真实 worker drain、下游真实浏览器大数据表格、长分页、导出下载和网络恢复 smoke 仍是 `documented-risk`。
- `import.process.requested` 是 file confirm 唯一 durable processing event，不是 inline fallback；具体发票 job 通过 session + selected file ids + batch type 精确归属于发票页，银行/发票任务和 outbox 不得互相阻断 Audit。
- `tests/test_audit_invoice_import_page.py` 覆盖 direct-canonical expected-set、关键字段、manual source-link 双向 equality、strict 发票同时保留 known legacy invoice-batch edge 的非阻断语义、unknown/non-invoice batch edge 的 fail-closed、file hash、job/outbox 和一次性 PostgreSQL 0001–0097 破坏性反证；`tests/test_platform_runtime_boundary_guards.py` 防止 inline/revert/import-file batch-column 旧链回流。

## 2026-07-15 多明细发票回归

- `tests/test_import_file_service.py`：不同商品/折扣行合并为一张整票；完全相同重复行仍进入 duplicate audit。
- `tests/test_audit_invoice_import_page.py`：历史 component rows 按整票合计比较；完全相同重复行不二次加总。
- `tests/test_import_audit_repair_ops.py`：canonical 金额恢复、source batch guard、dry-run plan 幂等和 rollback manifest。
- `tests/test_import_audit_repair_ops.py`：精确生命周期目标、succeeded job 证明、registered row/canonical/source-link 闭环、terminal 幂等、活跃 job/闭环缺失 fail-closed、batch/file 原子事务 precondition。
- `tests/test_import_audit_repair_ops.py`：精确 reverted batch payload normalization、terminal 幂等、job/canonical ownership fail-closed、fingerprint 与单表写范围。
- `tests/test_app_postgres_mode_integration.py::test_controlled_import_repair_restores_only_exact_downgraded_lifecycle`：真实 PostgreSQL 上模拟 stale preview 降级，验证受控 repair 恢复并再次 dry-run 幂等；本机未配置 `FIN_OPS_TEST_DATABASE_URL` 时显式 skip。

## 2026-07-22 Phase 27 写后零 fan-out 回归

- `tests/test_import_processing_service.py`、`tests/test_import_file_api.py`：发票 confirm 保留原子事实提交、source version、审计、幂等与失败回滚；普通结果不再携带 tax/input/output/pending/search/cost/workbench barrier targets，也不发布页面 refresh。
- 共享导入前端测试证明完成反馈不读取 Workbench 或等待跨页面 barrier；进项、销项、待找、税金、搜索和成本在各自页面访问时检查 current scope freshness。
- 旧的 write-operation 测试若要求写后存在 `*.read_model.refresh`，必须删除或改为“零下游页面事件 + 访问后 exact-scope 收敛”。
## 2026-08-10 视觉回归

- `web/src/test/ImportCenterPage.test.tsx` 继续保护发票专用复核字段和共享工作区交互，避免视觉收敛恢复银行流水字段污染。

## 2026-09-01 fresh entry 与显式放弃回归

- `tests/test_import_lifecycle_service.py` 覆盖 batch/file/session/job 状态聚合、分页和 PostgreSQL 事务化 discard；页面不再暴露“取最新活跃 session”读接口。
- `tests/test_import_file_service.py` 与 `tests/test_import_file_api.py` 覆盖 owner 隔离、幂等 discard 及 discard 后禁止 confirm。
- `web/src/test/ImportCenterPage.test.tsx` 覆盖每次进入 fresh、不读历史 sessionStorage、不请求活跃 session 列表、只刷新当前页面创建的 session，以及 discard 成功后才清本地预览。
