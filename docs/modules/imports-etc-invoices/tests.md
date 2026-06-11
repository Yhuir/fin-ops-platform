# ETC发票导入测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| 页面入口 | `web/src/pages/imports/ImportEtcInvoicesPage.tsx` | 只传 `mode="etc_invoice"`，共享 `ImportWorkflowPage` 改动会影响银行流水和发票导入 |
| 共享工作流 | `web/src/components/imports/ImportWorkflowPage.tsx` | zip-only 上传、ready task selector、unavailable task reason、preview stale、job feedback、route unmount cleanup |
| 前端 ETC API mapper | `web/src/features/etc/api.ts` | `/api/etc/import/preview` multipart、长超时、`task_id`、snake_case/camelCase、background job payload、stale error 映射 |
| HTTP routes | `server.py` `/api/etc/import/preview`、`/api/etc/import/confirm`、`/api/etc/reconciliation-tasks*`、`/api/etc/business-batches*` | task version/hash 校验、structured error、idempotent job、queue unavailable、legacy import route |
| Reconciliation task service | `EtcReconciliationTaskService` | ready/importing/imported/closed、confirmed item set hash、missing requirements、source files、delete/reopen invalidating preview |
| Zip parser/filter | `etc_document_parsers.py`、`etc_reconciliation_zip_filter.py`、`EtcService.inspect_import_zips(...)` | corrupted zip、重复发票、组合金额匹配、多 requirement 分配、非 ETC evidence |
| ETC import service | `EtcService.preview_import_zips(...)`、`confirm_business_batch_import(...)` | import session freshness、duplicate/idempotency、attachments、business batch merge、partial success |
| Import processing | `ImportProcessingService.execute_etc_invoice_import_confirm_job(...)` | 创建/复用 task-scoped business batch、background progress、mark imported/failed、canonical invoice sync |
| Derived lifecycle | `RuntimeWorkerDerivedLifecycle.refresh_after_etc_invoice_sync(...)`、`DerivedDataLifecycleService` | `etc_import_confirmed` 必须刷新 Workbench、invoice lifecycle、tax offset、cost statistics、historical ETC repair、search |
| App Status / worker | `import` worker、`app_status_*_registry.py` | `etc_invoice_import` job readiness、`import.process.requested` envelope、全局 status 不能误判 ready |

## 场景覆盖清单

- ETC 导入页只接受 `.zip`，非 zip 文件在前端拒绝，后端也返回 `invalid_etc_import_request`。
- 没有 ready reconciliation task 时不得预览；unavailable task 必须展示 blocker。
- zip preview 必须根据 confirmed reconciliation task 过滤发票，展示 audit counts、missing requirements 和 filter status。
- task reopen、task version/hash 变化、canonical invoice 变化或 import session 变化后，confirm 必须返回 `stale_reconciliation_task_preview` 或 `preview_stale`。
- confirm 必须创建 `etc_invoice_import` background job，并能在 import-job worker 模式下以 `etc_invoice_import.confirm` processor 异步处理。
- confirm job 必须创建/复用 task-scoped business batch，导入匹配发票，写入 task import status，失败时 mark import failed。
- ETC import result 必须同步 canonical invoices，且不与 manual invoice 或不同 invoice number 的相同金额发票错误合并。
- confirm 完成后必须触发 `etc_import_confirmed`，刷新税金抵扣、成本统计、关联台和 search。
- 后续 business batch OA draft/manual submitted/delete 必须保护 summary row、散票释放和关联台 relation 取消。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_etc_reconciliation_service.py`、`tests/test_etc_backend.py` | 覆盖 task 状态、zip filter/matching、金额组合、重复发票、business batch 状态、manual OA status、delete/release。 |
| 2. Service-layer tests | 适用 | `tests/test_etc_backend.py`、`tests/test_import_job_queue.py`、`tests/test_cleanup_orphan_etc_reconciliation_tasks_tool.py`、`tests/test_historical_etc_business_batch_migration_service.py` | 覆盖 ETC service、import job processor、reconciliation task cleanup、migration/linking/idempotency。 |
| 3. API contract tests | 适用 | `tests/test_etc_backend.py`、`web/src/test/EtcApi.test.ts` | 覆盖 `/api/etc/import/*`、reconciliation task API、business batch API、structured errors、background job payload。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_import_job_queue.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_tax_offset_api.py` | 覆盖 import worker、`etc_import_confirmed` lifecycle、tax/cost/workbench refresh、App Status job/readiness。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/ImportCenterPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` | 覆盖 ETC standalone route、preview/confirm/stale/unmount、API mapper、business batch UI、global job status。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_etc_backend.py`、`tests/test_workbench_v2_api.py` | 覆盖 task-aware zip import -> business batch -> canonical invoice -> Workbench summary/open row -> submitted/delete recovery。 |
| 7. Existing feature regression tests | 适用 | 上述全部，以及 `docs/modules/etc-tickets/tests.md`、`docs/modules/tax-offset/tests.md`、`docs/modules/cost-statistics/tests.md` | 每次改 ETC import、business batch、canonical invoice、summary row 或 lifecycle 时，都必须回归下游页面旧行为。 |

## 历史 bug 回归库

| 风险 | 保护测试 |
| --- | --- |
| 非 zip 上传误入 ETC import | `tests/test_etc_backend.py::EtcApiTests::test_preview_rejects_non_zip_upload`、`web/src/test/ImportCenterPage.test.tsx` ETC non-zip test |
| 没有 ready task 仍允许 preview | `tests/test_etc_backend.py::EtcApiTests::test_etc_import_preview_requires_ready_task_even_when_no_tasks_exist` |
| task reopen 后旧 preview 仍可确认 | `tests/test_etc_reconciliation_service.py::EtcReconciliationServiceTests::test_reopen_returns_to_reviewing_and_invalidates_zip_preview` |
| task/hash 变化后 confirm 未提示重新预览 | `web/src/test/EtcApi.test.ts` stale reconciliation preview test、`web/src/test/ImportCenterPage.test.tsx` stale task preview test |
| canonical invoice 变化后旧 preview 可确认 | `tests/test_etc_backend.py::EtcApiTests::test_etc_import_confirm_returns_preview_stale_when_canonical_invoice_changes_after_preview` |
| confirm 重复请求产生重复导入 | `tests/test_etc_backend.py::EtcApiTests::test_etc_confirm_repeated_session_returns_same_job_without_duplicate_import` |
| partial success 被当作完整成功 | `tests/test_etc_backend.py::EtcApiTests::test_etc_confirm_job_partial_success_when_some_items_fail` |
| manual invoice 与 ETC import canonical 重复 | `tests/test_etc_backend.py::EtcApiTests::test_etc_import_syncs_to_canonical_invoices_and_dedupes_manual_invoice` |
| 已提交 ETC business batch 删除后 summary/relation 未释放 | `tests/test_etc_backend.py::EtcApiTests::test_submitted_etc_business_batch_delete_releases_summary_and_deletes_local_task`、`tests/test_etc_backend.py::EtcApiTests::test_submitted_etc_business_batch_delete_cancels_summary_relation_without_restoring_oa_bank_pair` |

## 关键 smoke flows

- ETC 对账任务创建 -> 上传信用卡账单/票根/补充凭证 -> 确认 task -> `/imports/etc-invoices` 选择 ready task -> 上传 zip -> preview -> confirm -> import worker/job 完成 -> task imported -> ETC business batch imported。
- ETC import confirm -> canonical invoice sync -> `etc_import_confirmed` -> 关联台 open 区散票/summary、税金抵扣、成本统计刷新。
- task 被 reopen 或 source file 删除 -> 旧 zip preview invalidated -> confirm 返回 stale -> 前端清空 preview 并要求重新预览。
- business batch 创建 OA 草稿 -> 用户手工确认 submitted -> 关联台展示 folded `etc_invoice_summary`；删除 submitted batch -> summary 释放、relation 取消、散票回到未配对。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_etc_backend \
  tests.test_etc_reconciliation_service \
  tests.test_import_job_queue \
  tests.test_derived_data_lifecycle_service \
  tests.test_runtime_worker_registry \
  tests.test_app_status_overview_service \
  tests.test_cleanup_orphan_etc_reconciliation_tasks_tool \
  tests.test_historical_etc_business_batch_migration_service \
  tests.test_link_existing_etc_batches_tool \
  tests.test_migrate_historical_etc_business_batches_tool \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_etc_batch_oa_api_tags_wait_only_for_bank \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_etc_batch_oa_bank_amount_mismatch_keeps_mismatch_tag_without_invoice \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_historical_etc_relation_tags_oa_and_injects_summary_row \
  -v

cd web && npm test -- --run \
  src/test/EtcApi.test.ts \
  src/test/ImportCenterPage.test.tsx \
  src/test/EtcTicketManagementPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

`scripts/verify.sh test` 会运行后端 `unittest discover`、前端 test 和 build，因此 nightly CI 会覆盖本模块现有自动化测试。真实大 zip、真实对象存储、真实 OA 草稿和真实 worker drain 仍需 staging 或发布前 smoke。

## 未测风险

- 真实票根网 zip、PDF/XML 混合包、超大 zip、异常编码、重复票号和缺失附件样本未由本地 fixture 完全覆盖。
- 真实对象存储、Postgres/RabbitMQ/Redis/systemd import worker drain、worker crash/retry、RabbitMQ wakeup 未由本地单测完全证明。
- 真实 OA 草稿创建、人工提交确认、Nginx `/api/` 和 `/fin-ops-api/` 代理路径仍需发布后 smoke。
- 大数据 ETC business batch 列表、长任务源文件、真实浏览器导出/删除/网络恢复仍是 `documented-risk`。
