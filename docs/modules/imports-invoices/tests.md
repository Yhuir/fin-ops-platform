# 发票导入测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| 页面入口 | `web/src/pages/imports/ImportInvoicesPage.tsx` | 只传 `mode="invoice"`，共享工作流改动会同时影响银行流水和 ETC 导入 |
| 共享工作流 | `web/src/components/imports/ImportWorkflowPage.tsx` | 每文件票据方向、preview stale、重复审计、session restore、route unmount cleanup、job feedback、read-only 导入门禁 |
| Browser e2e | `web/e2e/imports-invoices-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 真实 Chromium 上传两份发票、选择销项/进项方向、慢预览期间预览/清空/确认动作锁定且只提交一次 preview、预览 audit/重复明细/未导入项/需复核文案、损坏文件混合上传 file-level error 且 confirm 只提交正常文件 ID、确认后触发 Workbench refresh 并清空草稿；confirm 后继续打开销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计并断言下游 `read_model_status=fresh` 与导入影响行；导入页和下游成功节点检查没有导入失败/后台导入失败/read model 失败可见残留；`preview_stale` 和 confirm failure 必须错误可见、无 success、无 Workbench refresh；read-only 用户不能上传/预览/确认导入 |
| 前端 API mapper | `web/src/features/imports/api.ts` | multipart `file_overrides`、`batch_type`、snake_case/camelCase、`preview_stale` 错误映射、job/session shape |
| HTTP routes | `server.py` `/imports/files/preview`、`/imports/files/confirm`、`/imports/files/retry`、`/imports/files/sessions/{session_id}`、legacy `/imports/preview`、`/imports/confirm` | files/session API 与 legacy JSON API 并存；confirm 必须防 stale、unknown selected ids 和重复提交 |
| File import service | `FileImportService` | 损坏 Excel file-level error、模板识别、session/file/batch id、selected files confirm、预览审计 |
| Normalization core | `ImportNormalizationService` | input/output invoice identity、digital invoice number fallback、重复/疑似重复、ETC canonical merge、source links、tags |
| Import processing | `ImportProcessingService` | file confirm job 后必须执行发票生命周期、tax/cost/workbench scope 计算和 state persistence |
| Derived lifecycle | `DerivedDataLifecycleService` | `invoice_import_confirmed` 必须先刷新 `invoice_lifecycle`，再影响待找发票、税金、进项/销项/OA 待付款、成本、搜索 |
| Read model / worker | `runtime_worker_handlers.py`、runtime queue、App Status registries、`write_operation_slo_audit` | import job 成功不等于下游 fresh；worker/readiness 失败必须在 App Status 暴露；真实发票确认后应能审计到 Workbench、Workbench relation、invoice lifecycle、search、待找发票、进项使用、销项收款、OA 待付款、成本统计和税金抵扣 refresh scopes |

## 场景覆盖清单

- 发票导入页必须发送每文件方向：`input_invoice` / `output_invoice`。
- Browser e2e 必须覆盖发票导入页真实选择控件、预览按钮禁用/启用、慢预览 in-flight 动作锁定、审计汇总、重复项明细、未导入项明细、确认导入和 Workbench refresh 调用。
- read_export_only 用户必须能打开发票导入页但不能选择文件、预览或确认导入。
- 预览必须显示重复审计 counts、duplicate groups 和 review copy。
- 路由切换、卸载、重挂载、sessionStorage 恢复时不能丢失已选文件、预览结果或 in-flight preview 结果。
- `preview_stale` 必须映射为重新预览提示，不能继续确认旧结果，不能展示“已确认导入”，不能刷新 Workbench 或下游页面。
- confirm API/worker 入队失败必须错误可见，不能展示“已确认导入”，不能刷新 Workbench 或下游页面。
- 损坏 Excel 必须是 file-level `unrecognized_template`，不能让整个 preview 请求崩溃。
- 发票 `信息汇总表` 模板必须识别 `数电号码`、`购方企业名称`、`购方税号`、`销方企业名称`、`销方税号`、`商品名称` 等表头别名，并跳过末尾 `份数：...金额：...` 汇总页脚。
- 服务器 PostgreSQL runtime 下，发票预览完成后的 import fact dirty/outbox 持久化必须匹配当前 partial unique index；`job.outbox_events` dedupe conflict predicate 使用 `status = 'pending'`，不能回退到旧的 `pending/processing` 合同。
- 240 行合成发票同文件重复组必须只产生一个 confirmable representative，其余进入 duplicate audit / skipped count。
- input/output invoice identity 必须覆盖稳定号码、占位电子发票号、弱 fingerprint、跨批次重复、批内重复。
- ETC 来源或 tag 指向 ETC 时，input invoice import 需要合并 canonical invoice 而不是产生重复发票。
- confirm 必须跳过重复行、更新 source status、持久化 source links，并对 later preview batch 的重复保持幂等。
- `invoice_import_confirmed` 必须刷新 Workbench、Workbench relation/matching、invoice lifecycle、tax offset、cost statistics 和 search。
- 下游页面必须通过 read model freshness/source versions 判断结果；不能把导入确认返回当作所有页面 fresh。

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_import_service.py`、`tests/test_import_preview_audit.py` | 覆盖发票 identity、重复/疑似重复、占位电子发票号 fallback、ETC canonical merge、批内/跨批重复、source links。 |
| 2. Service-layer tests | 适用 | `tests/test_import_file_service.py`、`tests/test_import_job_queue.py`、`tests/test_import_formalization_api.py`、`tests/test_derived_data_lifecycle_service.py` | 覆盖 file/session preview/confirm、stale preview、job queue、retry/original file retention、derived lifecycle fan-out。 |
| 3. API contract tests | 适用 | `tests/test_import_api.py`、`tests/test_import_file_api.py`、`tests/test_workbench_v2_api.py`、`tests/test_tax_offset_api.py`、`tests/test_input_invoice_usage_api.py`、`tests/test_oa_pending_payment_api.py`、`tests/test_output_invoice_collection_api.py` | 覆盖 import API shape、`batch_type`、`preview_stale`、job payload、下游 read model status/source version 字段。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_import_job_queue.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py`、`tests/test_invoice_lifecycle_page_integration.py`、`tests/test_tax_offset_api.py`、`tests/test_write_operation_slo_audit.py` | 覆盖 import worker、invoice lifecycle 顺序、tax month cache invalidation、App Status/readiness，并用 `invoice_import_confirmed` write-operation profile 防止真实发票确认少刷新下游 read model 时仍被判定闭环。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/ImportCenterPage.test.tsx`、`web/src/test/ImportsApi.test.ts`、`web/src/test/AppStatusIndicator.test.tsx`、`web/e2e/imports-invoices-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | 覆盖每文件方向、预览审计、慢预览动作锁定、重复明细、未导入项明细、错误提示、session restore、route unmount、API mapper、全局 status popover，以及真实浏览器中的上传/选择/确认交互、损坏文件混合、preview stale/confirm failure、下游页面 fresh read model 展示、成功后无导入失败/后台导入失败/read model 失败可见残留和 read-only 导入门禁。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_workbench_v2_api.py`、`tests/test_tax_offset_api.py`、`tests/test_invoice_lifecycle_page_integration.py`、`web/e2e/imports-invoices-flow.spec.ts` | 覆盖 import confirm -> stale protection -> workbench/tax/invoice lifecycle 下游刷新；Browser e2e 覆盖 confirm 后 Workbench refresh、销项收款/进项使用/税金抵扣/待找发票/OA 待付款/成本统计 fresh read model 和导入影响行，损坏文件混合时只提交正常文件 ID，也覆盖失败时不刷新 Workbench；导入页和各下游成功节点都会检查无错误残留。真实 worker drain 和 search 外层 UI 仍需 staging/后续 smoke。 |
| 7. Existing feature regression tests | 适用 | 上述全部，以及下游模块测试矩阵、`web/e2e/imports-invoices-flow.spec.ts` | 每次改 shared import、invoice fact、lifecycle、read model 或 App Status 时，都必须回归发票导入和下游页面旧行为。 |

## 历史 bug 回归库

| 风险 | 保护测试 |
| --- | --- |
| 占位电子发票号遮蔽稳定 code+number key | `tests/test_import_service.py::ImportNormalizationServiceTests::test_invoice_placeholder_digital_number_does_not_mask_stable_code_number_key` |
| 相同数字发票号没有被归入重复组 | `tests/test_import_preview_audit.py::ImportPreviewAuditTests::test_same_digital_invoice_number_is_grouped_as_duplicate` |
| 弱 fingerprint 被误用导致不同发票合并 | `tests/test_import_service.py::ImportNormalizationServiceTests::test_upsert_etc_invoice_does_not_reuse_weak_fingerprint_when_invoice_number_changed` |
| 既有 canonical invoice 读取时保留过期弱 fingerprint | `tests/test_import_service.py::ImportNormalizationServiceTests::test_existing_canonical_invoice_drops_weak_fingerprint_on_load` |
| ETC canonical invoice 与 input invoice import 重复 | `tests/test_import_service.py::ImportNormalizationServiceTests::test_input_invoice_import_merges_existing_etc_canonical_invoice_without_duplicate` |
| 预览后源事实变化仍允许确认 | `tests/test_import_file_service.py::ImportFileServiceTests::test_confirm_session_rejects_stale_preview_when_existing_records_change`、`tests/test_workbench_v2_api.py::WorkbenchV2ApiTests::test_import_file_confirm_returns_preview_stale_when_existing_records_change` |
| 大重复组被全部当作可确认行 | `tests/test_import_file_service.py::ImportFileServiceTests::test_preview_bounds_large_invoice_duplicate_group_to_one_confirmable_row` |
| 发票导入路由重挂载丢失预览或选择 | `web/src/test/ImportCenterPage.test.tsx` 中 invoice import session restore / navigating away tests |
| 发票慢预览期间用户重复触发 preview、清空或确认造成重复请求/半写状态 | `web/e2e/imports-invoices-flow.spec.ts` 的 slow preview Browser 回归，断言预览/清空/确认动作锁定且只提交一次 preview |
| 损坏发票文件导致整个 preview 崩溃，或 confirm 误提交不可导入文件 | `web/e2e/imports-invoices-flow.spec.ts` 的 corrupt mixed Browser 回归，断言 file-level error、未导入项明细和 `selected_file_ids` 只包含正常文件 |
| 发票导入确认后下游页面读取 stale read model 却显示导入成功 | `web/e2e/imports-invoices-flow.spec.ts` 的 downstream fresh Browser 回归，断言销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计 API 返回 `read_model_status=fresh` 且页面展示导入影响行 |
| 发票导入确认或下游 fresh 成功后页面仍残留导入失败/read model 失败提示 | `web/e2e/imports-invoices-flow.spec.ts` 的 success visible-error guard，断言导入页和六个下游成功节点没有导入失败、后台导入失败或 read model 失败等可见错误残留 |
| 发票导入 `preview_stale` 仍显示成功或刷新下游 | `web/e2e/imports-invoices-flow.spec.ts` 的 preview stale Browser 回归，断言错误可见、无 success、无 Workbench refresh |
| 发票导入 confirm 失败后显示成功或刷新下游 | `web/e2e/imports-invoices-flow.spec.ts` 的 confirm failure Browser 回归，断言错误可见、无 success、无 Workbench refresh |
| 发票文件确认 background job 在 App Status 中落到泛化导入域 | `tests/test_import_file_api.py::ImportFileApiTests::test_confirm_files_imports_only_selected_files_from_session` 断言 `affected_domains=["imports_invoices"]`、route `/imports/invoices`；`tests/test_app_status_overview_service.py` 覆盖泛化 import fallback |
| 发票 `信息汇总表` 表头别名不被识别，或汇总页脚被当作错误发票行 | `tests/test_import_file_service.py::ImportFileServiceTests::test_preview_accepts_invoice_summary_header_aliases`、`tests/test_import_file_service.py::ImportFileServiceTests::test_preview_detects_invoice_summary_without_template_override` |
| 服务器预览完成后 PostgreSQL import-fact outbox 入队 500 | `tests/test_postgres_repositories_core.py::test_save_imports_marks_read_models_dirty_and_outbox_event` 断言 `job.outbox_events` `ON CONFLICT` predicate 与 `0016` 后的 `outbox_events_dedupe_uidx` 一致；发布前可用一次性 PostgreSQL 库上传真实发票 Excel smoke |

## 关键 smoke flows

- 发票 Excel 上传 -> 每文件选择进项/销项 -> 预览 -> 确认 -> import worker/job 完成 -> `invoice_import_confirmed` / `import_state_changed` / `invoice_file_import_confirm` -> invoice lifecycle -> 待找发票、税金抵扣、进项发票使用、销项收款、OA 待付款、成本统计刷新。
- Staging write-flow audit：真实发票确认后运行 `PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit --json --operation invoice_import_confirmed --lookback-hours 24`，必须看到 Workbench、Workbench relation、invoice lifecycle、search、待找发票、进项使用、销项收款、OA 待付款、成本统计和税金抵扣 refresh scopes 通过 SLO。
- 发票 `信息汇总表` Excel 上传 -> 选择进项/销项 -> 表头别名归一 -> 预览行数排除末尾汇总页脚 -> 明细行进入重复审计和确认。
- 真实 PostgreSQL runtime smoke：5 个真实发票 Excel 上传 -> preview 返回 200 -> `preview_ready` 391 行 -> `app.import_batches`、`app.import_batch_rows`、`app.import_files` 和 `job.outbox_events(import.fact.changed)` 均成功写入。
- Browser e2e smoke：两份发票 XLSX 上传 -> 分别选择销项/进项 -> 预览 audit/重复明细/需复核文案 -> 确认导入 -> `/api/workbench` refresh -> 草稿清空 -> 无导入失败/后台导入失败/read model 失败可见残留。
- Browser downstream fresh smoke：发票导入确认 -> 打开销项收款、进项使用、税金抵扣、待找发票、OA 待付款和成本统计 -> 每个页面 API 返回 `read_model_status=fresh` -> 页面展示导入影响行 -> 无导入失败/后台导入失败/read model 失败可见残留。
- Browser slow-preview smoke：两份发票 XLSX 上传 -> 分别选择销项/进项 -> preview request in-flight -> 预览/清空/确认按钮禁用 -> 请求完成后恢复，且只提交一次 preview。
- Browser corrupt-file smoke：损坏发票文件 + 正常发票文件混合上传 -> 损坏文件作为 file-level error 进入未导入项 -> confirm 只提交正常文件 ID -> Workbench refresh。
- Browser negative smoke：两份发票 XLSX 上传 -> 预览 -> confirm 返回 `preview_stale` 或 500 -> 错误可见 -> 无“已确认导入” -> 不刷新 `/api/workbench`。
- 240 行同文件重复发票 -> preview audit 只保留一个 confirmable representative -> duplicate group 展示 240 行，skipped count 为 239。
- 预览后手工导入或另一个导入批次改变发票事实 -> 当前 confirm 返回 `preview_stale` -> 前端要求重新预览。
- 发票导入确认 -> 关联台 read model invalidation -> matching/candidate 重新生成，不使用旧 cache。
- input invoice import 与 ETC canonical invoice 相遇 -> 只更新同一 canonical invoice 并保留 ETC tag。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_import_api \
  tests.test_import_service \
  tests.test_import_file_service \
  tests.test_import_file_api \
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
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_invoice_import_confirm_invalidates_workbench_read_model \
  -v

cd web && npm test -- --run \
  src/test/ImportsApi.test.ts \
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
- Browser e2e 当前覆盖 deterministic mock 下的发票上传、方向选择、预览审计、慢预览动作锁定、损坏文件混合、确认、Workbench refresh，以及销项收款/进项使用/税金抵扣/待找发票/OA 待付款/成本统计的 fresh read model 展示；search、真实 worker drain、下游真实浏览器大数据表格、长分页、导出下载和网络恢复 smoke 仍是 `documented-risk`。
- 共享 `import.process.requested` 仍是多导入域 fallback；具体发票文件确认通过 `file_import.source.affected_domains` / `source.route` 精确指向发票导入页。
