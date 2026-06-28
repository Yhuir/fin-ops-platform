# 税金抵扣测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

税金抵扣横跨进项/销项发票、税局认证结果、ETC/OA 附件发票、计划保存、direct API payload 和 App Status。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 税额试算 | `TaxOffsetService` | 销项税额、已认证进项税额、未认证计划进项税额、可抵扣税额、应纳/留抵结果不能由页面重算。 |
| 发票生命周期 | `InvoiceLifecyclePolicy`、direct read boundary | `certified_status` / `is_locked_certified` shape 保持兼容；页面不能私有定义认证状态。 |
| 进项计划行 | Invoice repository / `app.invoices`、direct tax service | 真实导入进项票和已 promotion 的 OA 附件正式发票按开票月份进入计划；收据/未知附件不能进入。 |
| 已认证结果 | `TaxCertifiedImportService`、`TaxCertifiedImportApplicationService` | preview、confirm、重复导入去重、行级识别状态、计划内/计划外拆分。 |
| 计划保存 | `TaxOffsetPlanService` | 写权限、idempotency key、direct source version 乐观锁、summary snapshot。 |
| API/read path | `/api/tax-offset*`、`TaxOffsetQueryService` | 页面 GET 直接调用 `TaxOffsetService` 组装 payload；不读取 SQL read model / Redis fresh-gate，也不返回 freshness 字段。 |
| cache warmup / historical SQL tables | `TaxOffsetRuntimeService`、`tax_offset_cache_warmup`、历史 `read_model.tax_offset_*` | 不再投递 `tax_offset.read_model.refresh`；页面 GET 不读取 SQL read model / Redis fresh-gate，也不返回 freshness 字段；旧 cost/tax SQL projection 已删除。 |
| 导入 job | import job repository / polling API | confirm 可转后台任务；前端 modal 必须保持 processing，直到 job 结果完成。 |
| App Status / runtime diagnostics | invoice lifecycle / tax certified import / cache warmup | 不能由页面本地状态推断，也不能作为页面 GET 合同字段。 |
| 前端交互 | `TaxOffsetPage`、`web/src/features/tax/api.ts`、`web/src/components/tax/*` | loading/abort/remount、权限、导入 modal、drag/drop、搜索、排序、筛选、drawer、高亮、空状态、计划保存。 |
| 跨模块 fan-out | invoice import、ETC import、tax certified import、pending invoice rules、workbench relation、invoice lifecycle | 下游 affected scope/outbox/cache warmup 必须覆盖税金抵扣，同时不能恢复无关页面 read model。 |

## 场景覆盖清单

Spec-first Browser e2e 审计入口：

- `e2e-spec.md`：税金抵扣页面 Browser e2e 验收合同。
- `e2e-coverage.md`：Spec ID 到现有 Playwright/Vitest/API/integration 的映射和缺口。

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 税金试算核心规则 | P0 | `tests/test_tax_offset_service.py` | covered | 销项/进项/已认证/计划选择、锁定已认证进项、应纳/留抵结果。 |
| 真实导入发票进入计划 | P0 | `tests/test_object_identity_policy.py`、`tests/test_tax_offset_service.py`、`tests/test_tax_offset_api.py` | covered | 导入进项票、OA 附件发票 canonical promotion、缺少 `evidence_type` 但带 `invoice_type=进项发票` 的正式附件发票、空真实数据不返回硬编码计划行。 |
| 已认证导入解析与去重 | P0 | `tests/test_tax_certified_import_service.py`、`tests/test_tax_offset_api.py` | covered | 文件解析、行级状态、唯一键 fallback、重复导入幂等。 |
| 已认证 preview/confirm/job polling API | P0 | `tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/TaxApi.test.ts` | covered | preview 权限、confirm 幂等、job payload contract、modal queued/running/completed；前端 confirm/job 成功后直接刷新当前月份页面数据且不请求 operation barrier。 |
| 权限 | P0 | `tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/tax-offset-flow.spec.ts` | covered | read endpoint 访问控制、preview/save 写权限、只读用户隐藏导入/保存；Browser 覆盖 read-export 可读不可写、forbidden/expired 零 tax protected API 和 admin 写入口可见。 |
| 计划保存/idempotency/version conflict | P0 | `tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts` | covered | 保存使用 direct source versions（存在时），重复请求幂等，stale source 返回 conflict；Vitest 锁定保存成功后直接重新读取 `/api/tax-offset` 且不请求 operation barrier；Browser 覆盖 409 冲突错误可见、不显示保存成功、不刷新成伪成功且保存按钮可恢复。 |
| API shape 与 metric | P1 | `tests/test_tax_offset_api.py`、`web/src/test/TaxApi.test.ts` | covered | month、calculate、summary、plan save、job mapper、structured metric。 |
| runtime local store scope | P0 | `tests/test_tax_offset_worker_rebuild_executor.py`、`tests/test_tax_offset_cache_warmup_executor.py` | covered | runtime local store 只保留兼容 snapshot persistence；worker/cache executor 通过 runtime 写入，不再依赖独立 read model service。 |
| Direct API/runtime no read-model worker | P0 | `tests/test_tax_offset_api.py`、`tests/test_tax_offset_service.py`、`tests/test_tax_offset_worker_rebuild_executor.py`、`tests/test_tax_offset_cache_warmup_executor.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_runtime_state_policy.py` | covered | 页面 API 直接返回业务 payload；runtime/cache executor 保持兼容边界；guard 防止 worker/AppStatus/production refresh path 重新依赖 page read-model projection。 |
| lifecycle fan-out | P0 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_tax_offset_api.py` | covered | 发票导入、认证导入、规则变更、OA rebuild 等事件刷新 tax offset，不误刷银行导入。 |
| Workbench relation fan-out | P1 | `web/e2e/workbench-relations-tax-offset-fanout.spec.ts`、`docs/modules/workbench-relations/e2e-coverage.md` | covered | Browser 覆盖 Workbench confirm 后重新请求 `/api/tax-offset`，读取 direct tax offset payload 并展示 relation 影响后的进项计划行。 |
| App Status / registry | P1 | `tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py` | covered | route/domain registry；`tax-offset` / `cost-tax` read-model worker 已删除。 |
| migration/schema | P1 | `tests/test_postgres_migrations.py`、`tests/test_postgres_state_store.py` | covered | certified import、tax offset plans、read model 表结构和状态存取。 |
| 前端页面交互 | P1 | `web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts` | covered | loading abort、remount reload、只读权限、导入 modal、drag/drop、非 Excel 拒绝、recalculate、save、搜索/排序/筛选、drawer、高亮、empty；Browser e2e 覆盖真实 Chromium 下的 read-export/forbidden/expired/admin 权限细分、试算、保存、409 conflict 不伪成功、modal preview/confirm、页面刷新、保存/导入成功后无保存失败、导入失败或后台同步失败残留、390px 窄屏大表搜索/排序/筛选/横向滚动/按钮无遮挡，以及 direct payload 首屏不出现页面级 read model retry；Vitest 覆盖空 direct payload 显示真实空态。 |
| 真实外部环境 smoke | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres/Redis/RabbitMQ/systemd 验证 direct API、导入 job 和 cache warmup。 |

## 七类测试适用性

2026-06-28 modular IO 更新：旧 `cost_tax_sql_projection.py` 与税金 SQL runtime 测试已删除；税金抵扣当前测试事实源转为 direct API、业务 service、runtime/cache executor 和 boundary guard。历史 `read_model.tax_offset_*` 表仅作为迁移清理对象，不再作为页面或 worker 覆盖入口。

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_tax_offset_service.py`、`tests/test_tax_certified_import_service.py` | 覆盖税额试算、已认证锁定、计划内/外拆分、唯一键匹配、真实导入行归一化。 |
| 2. Service-layer tests | 适用 | `tests/test_tax_offset_cache_warmup_executor.py`、`tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`tests/test_postgres_state_store.py` | 覆盖 cache warmup executor、计划保存 service、导入 job repository、Postgres 状态边界。 |
| 3. API contract tests | 适用 | `tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`web/src/test/TaxApi.test.ts`、`web/e2e/tax-offset-flow.spec.ts` | 覆盖 `/api/tax-offset`、calculate、summary、plans、certified-import preview/confirm/job/list 的 response shape、权限和错误；Browser 额外保护 session gate 零 protected API 和 plan save 409 conflict 的用户可见错误合同。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_tax_offset_worker_rebuild_executor.py`、`tests/test_tax_offset_derived_lifecycle_executor.py`、`tests/test_tax_offset_cache_warmup_executor.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py`、`tests/test_platform_runtime_boundary_guards.py`、`tests/test_runtime_state_policy.py`、`tests/test_read_model_architecture_guards.py` | 覆盖 runtime/cache executor、derived lifecycle、cache warmup background job executor、runtime invalidation Redis delete best-effort、lifecycle fan-out 和 App Status；static guard 防止 cache warmup job creation/run/env helper、直接 read-model service upsert/persist、app invalidation wrapper 或 broad full-state `tax_offset_read_models` 写入回到 `Application`/executor。旧 SQL projection/runtime 测试已删除。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/TaxApi.test.ts`、`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/workbench-relations-tax-offset-fanout.spec.ts` | 覆盖用户可见 loading/error/empty/权限/导入/保存/搜索/排序/筛选/drawer/job polling，并用真实浏览器覆盖 read-export/forbidden/expired/admin 权限细分、StrictMode 下 modal confirm 后关闭与刷新、plan save 409 conflict 不伪成功、保存/导入成功后无错误残留、direct payload 首屏、390px 窄屏大表滚动和筛选弹层视口定位，以及 Workbench relation 后税金页 direct 重读。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/workbench-relations-tax-offset-fanout.spec.ts` | 覆盖认证导入 preview -> confirm/job -> 后端 invalidation -> 页面 direct 刷新；Browser e2e 覆盖用户从试算/保存到认证导入刷新后的可见结果、保存/认证导入成功后无错误残留、plan save conflict 防假成功，也覆盖 Workbench confirm -> tax offset direct payload -> relation 影响行展示；真实 staging smoke 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 tax offset tests，加 invoice lifecycle、pending invoice、ETC、workbench、cost statistics tests 的按改动选择扩展集 | 发票、ETC、关系、规则和 legacy read-model cleanup 都可能影响税金抵扣旧功能；`web/e2e/tax-offset-flow.spec.ts` 保护 direct 首屏、plan save conflict 不伪成功、已认证导入 modal 的 StrictMode mounted guard 回归，`web/e2e/workbench-relations-tax-offset-fanout.spec.ts` 保护 relation fan-out 不丢。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 长期 | 没有真实导入数据时，税金抵扣返回硬编码已认证或计划行。 | `tests/test_tax_offset_api.py::test_get_tax_offset_returns_month_rows_without_hardcoded_certified_items_by_default`、`tests/test_tax_offset_service.py::test_month_payload_is_empty_without_real_imports_or_explicit_month_data` | covered |
| 长期 | 已认证记录重复导入造成重复抵扣或重复显示。 | `tests/test_tax_certified_import_service.py::test_confirm_session_persists_month_records_and_deduplicates_reimport`、`tests/test_tax_offset_api.py::test_tax_certified_confirm_is_idempotent_for_same_session` | covered |
| 长期 | 已认证进项被用户再次作为未认证计划行选择，导致重复抵扣。 | `tests/test_tax_offset_service.py::test_month_payload_uses_real_certified_records_to_lock_matching_plan_and_split_outside_plan`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 长期 | API miss/stale 在请求线程同步 rebuild 并伪装 fresh。 | `tests/test_tax_offset_api.py::test_tax_offset_get_reads_direct_service_and_logs_miss_metrics`、`docs/modules/tax-offset/README.md` direct API contract | covered |
| 长期 | `all` refresh 被当作普通 tax offset 月份 payload。 | 已下线：不再存在 tax offset page read-model refresh worker；runtime/worker registry guard 防回归。 | retired |
| 长期 | 保存税金抵扣计划时没有校验 direct source version，导致基于旧数据保存。 | `tests/test_tax_offset_api.py::test_tax_offset_plan_save_rejects_stale_source_versions`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 长期 | 税金认证导入确认后页面不重读税金 direct payload。 | `tests/test_tax_offset_api.py::test_tax_certified_confirm_triggers_tax_offset_lifecycle_refresh`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 长期 | 银行流水导入误刷新税金抵扣。 | `tests/test_tax_offset_api.py::test_bank_import_confirm_does_not_invalidate_tax_offset_cache` | covered |
| 2026-06-13 / 2026-06-24 | 税金抵扣从 OA 附件 parser cache/Workbench 临时行读取发票，绕过统一 Invoice repository；或 OA 附件 payload 缺少 `evidence_type` 但带 `invoice_type=进项发票` 时未 promotion 成 canonical invoice facts。 | `tests/test_object_identity_policy.py::FinancialObjectIdentityPolicyTests::test_oa_attachment_invoice_evidence_classification_is_centralized`、`tests/test_tax_offset_service.py::test_month_payload_includes_oa_attachment_invoices_by_issue_month`、`tests/test_tax_offset_api.py::test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month` | covered |
| 2026-06-17 | React StrictMode effect replay 后，已认证导入 modal mounted guard 停留为 false，confirm 200 后直接 return，页面不关闭 modal、不刷新 tax offset。 | `web/e2e/tax-offset-flow.spec.ts` | covered |
| 2026-06-19 | Workbench relation 写入后，税金抵扣页没有重新读取 tax offset payload，导致 relation 影响后的进项计划行不可见或误报同步错误。 | `web/e2e/workbench-relations-tax-offset-fanout.spec.ts` | covered |
| 2026-06-26 | 页面级 freshness 回流影响页面空态、保存禁用或自动重试。 | `web/e2e/tax-offset-flow.spec.ts`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 2026-06-19 | 税金抵扣计划保存遇到 source/version conflict 时，页面可能误显示保存成功、刷新成伪成功或吞掉冲突错误。 | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_api.py::test_tax_offset_plan_save_rejects_stale_source_versions` | covered |
| 2026-06-19 | 税金抵扣权限只靠全局 role matrix，可能漏掉本页导入/保存入口、session gate 零 protected API 或 admin 写入口可见性。 | `web/e2e/tax-offset-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`tests/test_tax_offset_api.py` | covered |
| 2026-06-19 | 税金抵扣窄屏下 grid/flex 子项默认 `min-width:auto` 撑宽页面，导致共享横向滚动条失效，筛选弹层也可能被桌面 sidebar inset 推到 viewport 外；后续总 smoke 又发现共享筛选弹层在垂直空间不足时目标 checkbox 位于 viewport 外，已改为根据上下空间定位并让列表内部滚动。 | `web/e2e/tax-offset-flow.spec.ts`、`web/e2e/workbench-large-scroll-flow.spec.ts`、`web/src/test/WorkbenchPaneFilter.test.ts`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 2026-06-26 | 计划保存或已认证发票导入成功后前端重新请求 operation barrier，导致 direct API 迁移仍依赖 read model 收敛等待。 | `web/src/test/TaxOffsetPage.test.tsx::reloads directly after plan save without operation barrier` 和 queued import job 用例 | covered |

## 关键 smoke flows

1. `发票导入确认 -> invoice_lifecycle refresh -> tax offset direct API / cache warmup -> /tax-offset 页面展示`
2. `已认证导入 preview -> 行级状态/计划内外拆分 -> confirm/job queued -> tax_certified_import_confirmed lifecycle -> direct tax offset refresh -> 页面 summary 更新`
3. `用户调整计划勾选 -> calculate -> summary 更新 -> save plan with direct source versions/idempotency key -> direct tax offset refresh -> stale version conflict 可见且不伪成功，或幂等成功且无保存失败/后台同步失败残留`
4. `ETC 发票导入/业务批次变化 -> invoiceFactUpdated / lifecycle -> direct tax offset refresh -> 页面重新读取`
5. `pending invoice rules changed -> invoice_lifecycle -> tax_offset + cost_statistics affected scope/cache warmup -> 不恢复 no_oa_bank_batch/bank_account_balance/search page read model`
6. `Browser e2e: /tax-offset -> 取消一张进项计划 -> calculate -> 保存计划 -> 页内已认证发票导入 preview/confirm -> 刷新已认证结果 drawer -> 无保存/导入/后台同步失败残留`
7. `Browser e2e: /tax-offset -> Workbench confirm relation -> /tax-offset 重新读取 direct payload -> 显示 relation 影响后的进项计划行`
8. `Browser e2e: /tax-offset -> direct payload 首屏 -> 不显示页面级 read model retry -> 展示业务表格`
9. `Browser e2e: /tax-offset -> 修改计划 -> save plan 返回 409 conflict -> 错误可见、不显示保存成功、不刷新成伪成功 -> 保存按钮恢复可用`
10. `Browser e2e: /tax-offset -> read-export 可读无保存/导入入口 -> forbidden/expired 不调用 tax protected API -> admin 可见保存/导入入口`
11. `Browser e2e: /tax-offset -> 390px 窄屏 81/92 行大表 -> 搜索/排序/筛选 -> 共享横向滚动 -> 保存/导入按钮无遮挡`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_service tests.test_tax_certified_import_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api tests.test_import_job_queue -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_worker_rebuild_executor tests.test_tax_offset_derived_lifecycle_executor tests.test_tax_offset_cache_warmup_executor tests.test_platform_runtime_boundary_guards tests.test_runtime_state_policy -v
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_app_status_overview_service tests.test_postgres_state_store tests.test_postgres_migrations -v
cd web && npm test -- --run src/test/TaxOffsetPage.test.tsx src/test/TaxApi.test.ts src/test/AppStatusIndicator.test.tsx
cd web && npx playwright test e2e/tax-offset-flow.spec.ts e2e/workbench-relations-tax-offset-fanout.spec.ts
bash scripts/verify.sh docs
```

扩展回归按改动选择：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api tests.test_input_invoice_usage_api tests.test_cost_statistics_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend tests.test_derived_data_lifecycle_service -v
cd web && npm test -- --run src/test/App.test.tsx src/test/InputInvoiceUsagePage.test.tsx src/test/CostStatisticsPage.test.tsx
PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.runtime_worker_manifest --json
```

## Nightly CI 覆盖

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、frontend build 和 deterministic Playwright smoke，覆盖完整税金抵扣、认证导入、legacy read-model guard、App Status、前端测试集、`web/e2e/tax-offset-flow.spec.ts` 的浏览器权限细分、导入刷新闭环、保存/导入成功后无错误残留、plan save conflict 防假成功、direct payload 首屏和窄屏大表交互，以及 `web/e2e/workbench-relations-tax-offset-fanout.spec.ts` 的 Workbench relation -> tax offset direct payload fan-out。单轮模块验证只跑最小闭环。

## 未测风险

- 本地测试不连接真实税局认证 XLSX 大样本、真实 OA 附件发票缓存或真实 ETC 生产数据；真实数据格式变化需要发布前样本 smoke。
- 本地测试不跑真实 RabbitMQ/Redis/systemd smoke；direct API、导入 job 和 cache warmup 的真实收敛需要 staging 或夜间 CI/生产前 smoke。
- 前端 Vitest 与 deterministic Playwright 覆盖交互、job polling、真实 Chromium modal confirm/刷新闭环和 direct payload 首屏；仍不覆盖真实浏览器下载、超大表格性能、真实网络中断恢复和真实税局文件差异。
