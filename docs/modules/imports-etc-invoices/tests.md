# ETC发票导入测试矩阵

## 2026-07-14 MinIO worker wiring / confirmable count 增量

| 类别 | 覆盖 |
| --- | --- |
| 业务核心 | task/version/hash、ZIP allowlist、preview counts/fingerprint、partial/failure/retry |
| Service | durable session store、跨 store 实例重载、worker object storage 注入、worker 写入后的 API query reload、`begin_import` 幂等、terminal status |
| API contract | preview storage 503、confirm queue 503、旧 `/api/etc/import` 404、admin-only Audit |
| Read model / queue | zero own read model；page-owned import job/outbox gate；下游仅 impact targets |
| Frontend | ETC Audit 控件使用 `confirmable_count`、ZIP/task/preview/confirm 回归 |
| E2E integration | disposable PostgreSQL 0001–0098 store + Audit clean/destructive proof |
| Existing regression | ETC tickets、business batch/OA draft/delete、canonical linking、file/object migrations |

关键入口：`tests/test_etc_import_session_store.py`、`tests/test_audit_etc_import_page.py`、`tests/test_etc_backend.py`、`tests/test_import_processing_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`web/src/test/ImportCenterPage.test.tsx`。


> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| 页面入口 | `web/src/pages/imports/ImportEtcInvoicesPage.tsx` | 只传 `mode="etc_invoice"`，共享 `ImportWorkflowPage` 改动会影响银行流水和发票导入 |
| 共享工作流 | `web/src/components/imports/ImportWorkflowPage.tsx` | zip-only 上传、ready task selector、unavailable task reason、preview stale、job feedback、route unmount cleanup、read-only 导入门禁 |
| Browser e2e | `web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 真实 Chromium 加载 ready task、选择 task、上传 zip、预览 audit/导入项、`preview_stale`、`stale_reconciliation_task_preview` 清空预览、confirm 失败、确认后展示 background job feedback、ETC 票据/税金抵扣/成本统计下游 fresh read model，并断言成功节点没有导入失败/后台导入失败/read model 失败可见残留且不走通用 `/imports/files/*`；read-only 用户不能上传/预览/确认导入 |
| 前端 ETC API mapper | `web/src/features/etc/api.ts` | `/api/etc/import/preview` multipart、长超时、`task_id`、snake_case/camelCase、background job payload、stale error 映射 |
| HTTP routes | `server.py` `/api/etc/import/preview`、`/api/etc/import/confirm`、`/api/etc/reconciliation-tasks*`、`/api/etc/business-batches*` | task version/hash 校验、structured error、idempotent job、queue unavailable、legacy import route |
| Reconciliation task service | `EtcReconciliationTaskService` | ready/importing/imported/closed、confirmed item set hash、missing requirements、source files、delete/reopen invalidating preview |
| Zip parser/filter | `etc_document_parsers.py`、`etc_reconciliation_zip_filter.py`、`EtcService.inspect_import_zips(...)` | corrupted zip、重复发票、组合金额匹配、多 requirement 分配、非 ETC evidence |
| ETC import service | `EtcService.preview_import_zips(...)`、`confirm_business_batch_import(...)` | import session freshness、duplicate/idempotency、attachments、business batch merge、partial success |
| Import processing | `ImportProcessingService.execute_etc_invoice_import_confirm_job(...)` | 创建/复用 task-scoped business batch、background progress、mark imported/failed、保存 ETC metadata/PDF/XML 附件关系，并只关联已存在 canonical invoice |
| Import cleanup | `EtcReconciliationImportCleanupService`、`EtcBusinessBatchDeleteService` | 删除/重导只清理 ETC task/import batch/business batch 自有事实和 changed months，不调用通用 import service 删除或改写 canonical invoice |
| 页面访问收敛 | import processor、各消费页 fresh gate、`ReadModelRefreshGateway` | `etc_import_confirmed` 只提交 canonical metadata/source version，普通确认零页面 dirty/outbox；ETC 票据、Workbench/relation/matching、invoice lifecycle、tax offset、search、Cost 分别在访问或重新激活时按 exact scope 收敛；historical repair 不进入热路径 |
| App Status / worker | `import` worker、`app_status_*_registry.py`、`tests/test_platform_runtime_boundary_guards.py` | `etc_invoice_import` job readiness、`import.process.requested` envelope、全局 status 不能误判 ready，且 runtime ETC import link helper 不得调用 canonical invoice create API |

## 场景覆盖清单

- ETC 导入页只接受 `.zip`，非 zip 文件在前端拒绝，后端也返回 `invalid_etc_import_request`。
- 没有 ready reconciliation task 时不得预览；unavailable task 必须展示 blocker。
- zip preview 必须根据 confirmed reconciliation task 过滤发票，展示 audit counts、missing requirements 和 filter status。
- Browser e2e 必须覆盖 ready task selector、zip preview、audit/review copy、confirm job feedback、preview stale、stale task preview、confirm failure、ETC 票据/税金抵扣/成本统计下游 fresh read model，以及 ETC 导入不误走通用 files import API。
- read_export_only 用户必须能打开 ETC 发票导入页但不能选择 zip、预览或确认导入。
- 120 张合成 ETC 发票混合 zip preview 必须把有效发票、同包重复 XML、malformed XML file-level failure 分开计数，且 preview 不持久化发票记录。
- task reopen、task version/hash 变化、已存在 canonical invoice 关系变化或 import session 变化后，confirm 必须返回 `stale_reconciliation_task_preview` 或 `preview_stale`；页面不能展示“已开始后台导入”，其中 stale task preview 必须清空旧 preview 并要求重新预览。
- confirm API/worker 入队失败必须错误可见，不能展示“已开始后台导入”，不能把下游 read model 伪装成 fresh。
- confirm 必须创建 `etc_invoice_import` background job，并能在 import-job worker 模式下以 `etc_invoice_import.confirm` processor 异步处理。
- confirm job 必须创建/复用 task-scoped business batch，导入匹配发票，写入 task import status，失败时 mark import failed。
- PostgreSQL 模式下独立 worker 写入 task、business batch 和 ETC invoice 后，已在运行的 API query service 必须无需重启即可读到新状态；本地 file/memory backend 不启用该 reload。
- ETC import result 必须保存 ETC metadata/附件并关联已存在 canonical invoices；缺失 canonical invoice 时不得自动创建，也不得把不同 invoice number 的相同金额票据错误合并。
- runtime worker 的 ETC import link helper 必须只调用 `upsert_etc_invoice` 的 link-existing 入口；缺失 canonical invoice 时不得调用 `upsert_invoice`、`create_invoice` 或 `register_invoice` 等创建入口。
- 删除导入结果或 business batch 时不得调用通用 import service 做 legacy canonical cleanup；响应不得暴露 `removedCanonicalInvoiceCount` 之类旧清理字段。
- confirm 只有在 existing canonical metadata 真实变化时才触发精确月份 `etc_import_confirmed`；无匹配或幂等重放必须零 refresh。关联台、税金和 search 走直接 owner，成本由 Workbench publish 后有序收敛。
- 后续 business batch OA draft create/replay 不触发 downstream；manual submitted/not-submitted 只触发精确 `etc_business_batch_status_changed`，保护 summary/普通发票可见性但不直刷税金、成本或历史修复；delete 继续保护 summary row、ETC metadata 释放和关联台 relation 取消。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_reconciliation_service.py`、`tests/test_etc_backend.py` | 覆盖 task 状态、zip filter/matching、金额组合、重复发票、business batch 状态、manual OA status、delete/release。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py`、`tests/test_import_job_queue.py`、`tests/test_etc_reconciliation_import_cleanup_service.py`、`tests/test_etc_business_batch_delete_service.py`、`tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py` | 覆盖 ETC service、import job processor、reconciliation task cleanup、business batch delete、deterministic ETC relation enrichment/idempotency。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py`、`web/src/test/EtcApi.test.ts` | 覆盖 `/api/etc/import/*`、reconciliation task API、business batch API、structured errors、background job payload。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_import_job_queue.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_tax_offset_api.py`、`tests/test_cost_statistics_sql_runtime.py`、`tests/test_platform_runtime_boundary_guards.py` | 覆盖 mutation-sensitive existing link、精确 scope、`etc_import_confirmed`/`etc_business_batch_status_changed` lifecycle、Tax/Workbench 显式 import scope、Cost 页面访问时 Workbench→Cost 两阶段 gate、App Status job/readiness；旧 write-operation profile 的 publish fan-out expectation 不是当前合同，由 Phase 27-06 删除门禁处理。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/ImportCenterPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/imports-etc-invoices-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 覆盖 ETC standalone route、preview/confirm/stale/unmount、API mapper、business batch UI、global job status，以及真实浏览器 ready task/zip/confirm job、preview stale、stale task preview、confirm failure、ETC 票据/税金/成本下游 fresh read model 交互、成功后无导入失败/后台导入失败/read model 失败可见残留和 read-only 导入门禁。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py`、`tests/test_workbench_v2_api.py`、`web/e2e/imports-etc-invoices-flow.spec.ts` | 覆盖 task-aware zip import -> business batch -> ETC metadata/附件 -> Workbench summary/open row -> submitted/delete recovery；Browser e2e 覆盖导入页 preview/confirm job、失败时不误报 job success，并在 deterministic mock 下覆盖 ETC 票据、税金抵扣、成本统计最终 fresh 展示和成功后无错误残留；真实 worker 完成仍需 staging。 |
| 7. Existing feature regression tests | 适用 | 上述全部、`tests/test_platform_runtime_boundary_guards.py`、`docs/modules/etc-tickets/tests.md`、`docs/modules/tax-offset/tests.md`、`docs/modules/cost-statistics/tests.md`、`web/e2e/imports-etc-invoices-flow.spec.ts` | 每次改 ETC import、business batch、已存在 canonical invoice 关联、summary row 或 lifecycle 时，都必须回归下游页面旧行为，并保护 runtime worker 不恢复旧的 ETC canonical invoice 创建/cleanup 路径。 |

## 历史 bug 回归库

| 风险 | 保护测试 |
| --- | --- |
| 非 zip 上传误入 ETC import | `tests/test_etc_backend.py::EtcApiTests::test_preview_rejects_non_zip_upload`、`web/src/test/ImportCenterPage.test.tsx` ETC non-zip test |
| 没有 ready task 仍允许 preview | `tests/test_etc_backend.py::EtcApiTests::test_etc_import_preview_requires_ready_task_even_when_no_tasks_exist` |
| task reopen 后旧 preview 仍可确认 | `tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_reopen_returns_to_reviewing_and_invalidates_zip_preview` |
| task/hash 变化后 confirm 未提示重新预览 | `web/src/test/EtcApi.test.ts` stale reconciliation preview test、`web/src/test/ImportCenterPage.test.tsx` stale task preview test |
| canonical invoice 变化后旧 preview 可确认 | `tests/test_etc_backend.py::EtcApiTests::test_etc_import_confirm_returns_preview_stale_when_canonical_invoice_changes_after_preview` |
| Browser 中 `preview_stale` 仍展示后台导入成功 | `web/e2e/imports-etc-invoices-flow.spec.ts` 的 preview stale Browser 回归，断言错误可见、无“已开始后台导入”、不走通用 files confirm |
| Browser 中 stale reconciliation task preview 没清空旧预览 | `web/e2e/imports-etc-invoices-flow.spec.ts` 的 stale task Browser 回归，断言旧 preview 清空、preview 可重新执行、confirm 禁用 |
| Browser 中 confirm 失败仍展示后台导入成功 | `web/e2e/imports-etc-invoices-flow.spec.ts` 的 confirm failure Browser 回归，断言错误可见、无“已开始后台导入”、不走通用 files confirm |
| Browser 中 confirm 或下游 fresh 成功后仍残留导入失败/read model 失败提示 | `web/e2e/imports-etc-invoices-flow.spec.ts` 的 success visible-error guard，断言导入页、ETC 票据、税金抵扣和成本统计成功节点没有导入失败、后台导入失败或 read model 失败等可见错误残留 |
| confirm 重复请求产生重复导入 | `tests/test_etc_backend.py::EtcApiTests::test_etc_confirm_repeated_session_returns_same_job_without_duplicate_import` |
| 多 ZIP preview 对历史 MinIO 附件逐张重复下载并在 session 保存后重下载全部 ZIP，触发代理 504 | `tests/test_etc_backend.py::EtcServiceTests::test_preview_does_not_download_verified_object_attachments_for_existing_invoices`、`tests/test_etc_import_session_store.py::EtcImportSessionStoreTests::test_durable_save_does_not_redownload_archives_after_verified_write` |
| 59 ZIP / 38 个需求的全局组合搜索把不符合车牌和日期窗口的发票也纳入金额组合，并反复复制/排序全部中间金额状态，导致 CPU 长时间不返回且可能跨上下文误配 | `tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_zip_preview_excludes_unrelated_context_before_global_amount_combinations`、`test_zip_preview_bounds_six_invoice_search_with_many_context_candidates`，并使用真实 59 ZIP + 生产 task payload 做本地 task-aware 性能回归 |
| API 预览已把 ZIP 写入 MinIO，但独立 import worker 构造 `PostgresStateStore` 时未注入对象存储，confirm 在第一张发票前报 `Object storage is not configured for PostgreSQL file access.` | `tests/test_import_job_queue.py::ImportJobRepositoryTests::test_runtime_import_processor_configures_object_storage_for_durable_archives`，并在发布后用失败 session 重试验证 PostgreSQL + MinIO worker drain |
| 独立 worker 已成功写入 PostgreSQL，但常驻 API 仍返回启动时的 task/business batch/invoice 快照，页面表现为“导入后没反应” | `tests/test_etc_backend.py::EtcApiTests::test_etc_query_services_reload_worker_writes_from_postgres_state_store`，使用先创建 API service、后由另一组 worker service 写入的共享 PostgreSQL 语义 store 验证跨进程可见性 |
| ETC audit 的 `importable_count=0` 但 `confirmable_count>0` 时页面误显示“可导入 0”，掩盖 reconciliation allowlist 中可确认记录 | `web/src/test/ImportCenterPage.test.tsx` ETC preview audit 回归、`web/e2e/imports-etc-invoices-flow.spec.ts` 浏览器预览回归 |
| ETC confirm job 缺少 App Status task/domain/route metadata | `tests/test_etc_backend.py::EtcApiTests::test_etc_confirm_returns_background_job_and_imports_asynchronously` 断言 `affected_domains=["imports_etc_invoices","etc_tickets"]`、route `/imports/etc-invoices` 和 `source.task_id`；`tests/test_app_status_overview_service.py` 覆盖 registry/payload fallback |
| partial success 被当作完整成功 | `tests/test_etc_backend.py::EtcApiTests::test_etc_confirm_job_partial_success_when_some_items_fail` |
| 混合 zip 中有效发票、重复 XML 和坏 XML 未分离计数 | `tests/test_etc_backend.py::EtcServiceTests::test_preview_large_mixed_zip_keeps_valid_invoices_duplicates_and_failures_separate` |
| manual invoice 与 ETC import 关联重复 | `tests/test_etc_backend.py::EtcApiTests::test_etc_import_links_existing_canonical_invoices_and_dedupes_manual_invoice` |
| runtime ETC import worker 重新调用 canonical invoice 创建 API，或幂等重放仍持久化/伪造月份 | `tests/test_platform_runtime_boundary_guards.py::RuntimeWorkerEtcImportLinkExistingTests::test_runtime_etc_import_link_never_calls_canonical_invoice_create_api`、`test_existing_invoice_link_service_skips_persistence_and_scope_for_unchanged_replay`、`tests/test_import_service.py` replay regression |
| OA workflow 重连整批 canonical invoice，或 batch-only 前端事件污染 Tax/Cost | `test_etc_oa_workflow_methods_do_not_link_or_refresh_canonical_invoice_facts`、`test_etc_invoice_refresh_uses_changed_months_once_without_all_scope_or_duplicate_matching`、`test_cost_and_tax_pages_ignore_etc_batch_only_domain_events` |
| 删除/重导 ETC import 时重新调用旧 canonical cleanup helper | `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests::test_etc_paths_do_not_call_legacy_canonical_sync_helpers`、`tests/test_etc_reconciliation_import_cleanup_service.py`、`tests/test_etc_business_batch_delete_service.py` |
| 已提交 ETC business batch 删除后 summary/relation 未释放 | `tests/test_etc_backend.py::EtcApiTests::test_submitted_etc_business_batch_delete_releases_summary_and_deletes_local_task`、`tests/test_etc_backend.py::EtcApiTests::test_submitted_etc_business_batch_delete_cancels_summary_relation_without_restoring_oa_bank_pair` |

## 关键 smoke flows

- ETC 对账任务创建 -> 上传信用卡账单/票根/补充凭证 -> 确认 task -> `/imports/etc-invoices` 选择 ready task -> 上传 zip -> preview -> confirm -> import worker/job 完成 -> task imported -> ETC business batch imported。
- Browser e2e smoke：ready task 加载 -> 选择 ETC 对账任务 -> 上传两份 zip -> preview audit/新增/重复/附件补齐/异常项 -> confirm -> `etc_invoice_import` background job feedback -> ETC 票据/税金抵扣/成本统计 fresh read model 展示导入证据 -> 无导入失败/后台导入失败/read model 失败可见残留。
- Browser negative smoke：ready task 加载 -> zip preview -> confirm 返回 `preview_stale`、`stale_reconciliation_task_preview` 或 500 -> 错误可见 -> 无“已开始后台导入” -> 不走通用 `/imports/files/confirm`。
- 120 张合成 ETC 发票 + PDF + duplicate XML + malformed XML -> preview summary 分别报告 imported / duplicatesSkipped / failed，且 list invoices 仍为空。
- ETC import confirm -> ETC metadata/已存在 canonical invoice 真变更 -> 精确月份 `etc_import_confirmed` -> Workbench/税金/search；之后访问 Cost 时先收敛 Workbench 精确月份，再收敛 Cost 自身。无变化重放停在 link boundary。
- Staging/生产 smoke：真实 ETC zip confirm 后证明显式 import 合同中的 Workbench、Workbench relation、invoice lifecycle、tax offset 精确 scope 收敛；随后独立访问 Cost，证明 normal GET 的 Workbench dependency→Cost 两阶段链在门槛内 fresh。不得用 `workbench_shard_published` 或 import 直投 Cost 作为通过条件；search 是 cache clear，不属于 `*.read_model.refresh` profile。
- task 被 reopen 或 source file 删除 -> 旧 zip preview invalidated -> confirm 返回 stale -> 前端清空 preview 并要求重新预览。
- business batch 创建 OA 草稿 -> 用户手工确认 submitted -> 关联台展示 folded `etc_invoice_summary`；删除 submitted batch -> summary 释放、relation 取消；只有原本已存在于统一发票池的发票才可能回到普通发票视图。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_etc_backend \
  tests.test_etc_reconciliation_service \
  tests.test_import_job_queue \
  tests.test_derived_data_lifecycle_service \
  tests.test_runtime_worker_registry \
  tests.test_app_status_overview_service \
  tests.test_write_operation_slo_audit \
  tests.test_cleanup_orphan_etc_reconciliation_tasks_tool \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_etc_batch_oa_api_tags_wait_only_for_bank \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_etc_batch_oa_bank_amount_mismatch_keeps_mismatch_tag_without_invoice \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_historical_etc_relation_tags_oa_and_injects_summary_row \
  -v

cd web && npm test -- --run \
  src/test/EtcApi.test.ts \
  src/test/ImportCenterPage.test.tsx \
  src/test/EtcTicketManagementPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx

cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts
cd web && npx playwright test e2e/imports-etc-invoices-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/permissions-role-matrix.spec.ts

bash scripts/verify.sh docs
```

真实 staging/发布前 worker/read model 验证：

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
  --json \
  --operation etc_import_confirmed \
  --lookback-hours 24
```

该命令审计 ETC 导入后核心下游 `*.read_model.refresh` 事件；它不替代真实对象存储/OA 草稿/大 zip smoke，也不替代 search cache clear 和页面最终 fresh 展示检查。

## Nightly CI 覆盖

`scripts/verify.sh all` 会运行后端 `unittest discover`、前端 Vitest、build、deterministic Playwright smoke 和 docs check，因此 nightly CI 会覆盖本模块现有自动化测试、`web/e2e/imports-etc-invoices-flow.spec.ts` 的 confirm、downstream fresh 和成功后无错误残留，以及 `web/e2e/permissions-role-matrix.spec.ts` 的共享导入 read-only 门禁；ETC 导入 spec 也覆盖 confirm 后 ETC 票据、税金抵扣、成本统计 downstream fresh read model。真实大 zip、真实对象存储、真实 OA 草稿和真实 worker drain 仍需 staging 或发布前 smoke。

## 未测风险

- 本地已覆盖 120 张合成 ETC 发票、PDF、同包重复 XML 和 malformed XML preview 分离计数；真实票根网 zip、PDF/XML/TXT 混合包、超大 zip、异常编码、重复票号和缺失附件样本仍需 staging/manual smoke。
- 真实对象存储、Postgres/RabbitMQ/Redis/systemd import worker drain、worker crash/retry、RabbitMQ wakeup 未由本地单测完全证明；`write_operation_slo_audit --operation etc_import_confirmed` 已有本地契约测试，但仍需要 staging 中真实 ETC confirm 样本产生 recent outbox rows 才能证明真实 write-flow。
- 真实 OA 草稿创建、人工提交确认、Nginx `/api/` 和 `/fin-ops-api/` 代理路径仍需发布后 smoke。
- Browser e2e 当前覆盖 deterministic mock 下的 ready task zip preview/confirm job feedback、ETC 票据批次、税金抵扣和成本统计下游 fresh read model；大数据 ETC business batch 列表、真实 worker 完成后的 Workbench/search/historical repair 展示、长任务源文件、真实浏览器导出/删除/网络恢复仍是 `documented-risk`。
- 共享 `import.process.requested` 仍是多导入域 fallback；具体 ETC confirm job 通过 `etc_invoice_import.source` 精确指向 ETC 导入页和 ETC 票据域。

## 2026-07-15 历史失败覆盖证明

- `tests/test_audit_etc_import_page.py` 同时覆盖：failed session/job 的精确 task 已 `imported` 时只报告 covered warning；task 未正式完成时仍返回 blocking integrity issue。
- 覆盖判定复用 ETC 票据 Audit 常量，防止两个页面对同一 job/session 得出相反结果。
- 同一测试文件覆盖 `succeeded` session 对应 task 后续从 `imported` 合法推进到 `closed`；完整 terminal output edges 下不得产生 task-status mismatch，非法状态仍按原合同阻断。

## 2026-07-22 Phase 27 写后零 fan-out 回归

- `tests/test_import_processing_service.py`：ETC confirm 仍按真实 changed months 关联 canonical facts、保持幂等与 durable job recovery；无变化重放为零影响，普通完成不发布页面 read-model refresh。
- 共享导入前端与 ETC 页面测试：完成后只重新读取当前可见页，不等待 tax/search/workbench/cost barrier；其它页面首次访问时按自己的 freshness owner 收敛。
- 旧 `etc_import_confirmed` SLO 中“必须观察到核心下游 refresh 事件”的要求已被零 fan-out 合同取代。
