# 税金抵扣测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 修改前影响面清单

税金抵扣横跨进项/销项发票、税局认证结果、ETC/OA 附件发票、计划保存、read model freshness 和 App Status。任何改动都要先按下表做影响面评估：

| 影响面 | 当前事实源 | 需要关注的旧功能 |
| --- | --- | --- |
| 税额试算 | `TaxOffsetService` | 销项税额、已认证进项税额、未认证计划进项税额、可抵扣税额、应纳/留抵结果不能由页面重算。 |
| 发票生命周期 | `InvoiceLifecyclePolicy`、`invoice_lifecycle` read boundary | `certified_status` / `is_locked_certified` shape 保持兼容；页面不能私有定义认证状态。 |
| 进项计划行 | Invoice repository / `app.invoices`、SQL projection | 真实导入进项票和已 promotion 的 OA 附件正式发票按开票月份进入计划；收据/未知附件不能进入。 |
| 已认证结果 | `TaxCertifiedImportService`、`TaxCertifiedImportApplicationService` | preview、confirm、重复导入去重、行级识别状态、计划内/计划外拆分。 |
| 计划保存 | `TaxOffsetPlanService` | 写权限、idempotency key、read model scope/source version 乐观锁、summary snapshot。 |
| API/read cache | `/api/tax-offset*`、`TaxOffsetQueryService`、Redis hot cache、SQL read model | fresh gate 后才能缓存；miss/stale 返回 refreshing 并入队，不同步重建伪 fresh。 |
| read model refresh | `TaxOffsetReadModelRefreshService`、`tax-offset` worker、旧 `cost-tax` 兼容 worker、`ReadModelRefreshGateway` | 月份 shard 为 `YYYY-MM`；`all` 只 fan-out 到月份 shard，不作为普通月份 payload。 |
| 导入 job | import job repository / polling API | confirm 可转后台任务；前端 modal 必须保持 processing，直到 job 结果完成。 |
| App Status readiness | `tax_offset` read model、`tax-offset` worker、runtime snapshot | missing/refreshing/stale/failed/unavailable 必须从后端 runtime facts 解释，不能由页面本地状态推断。 |
| 前端交互 | `TaxOffsetPage`、`web/src/features/tax/api.ts`、`web/src/components/tax/*` | loading/abort/remount、权限、导入 modal、drag/drop、搜索、排序、筛选、drawer、高亮、空状态、计划保存。 |
| 跨模块 fan-out | invoice import、ETC import、tax certified import、pending invoice rules、workbench relation、invoice lifecycle | 下游 dirty scope/outbox 必须覆盖税金抵扣，同时不能误刷新无关 read model。 |

## 场景覆盖清单

Spec-first Browser e2e 审计入口：

- `e2e-spec.md`：税金抵扣页面 Browser e2e 验收合同。
- `e2e-coverage.md`：Spec ID 到现有 Playwright/Vitest/API/integration 的映射和缺口。

| 场景 | 优先级 | 当前覆盖 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 税金试算核心规则 | P0 | `tests/test_tax_offset_service.py` | covered | 销项/进项/已认证/计划选择、锁定已认证进项、应纳/留抵结果。 |
| 真实导入发票进入计划 | P0 | `tests/test_tax_offset_service.py`、`tests/test_tax_offset_api.py` | covered | 导入进项票、OA 附件发票 canonical promotion、空真实数据不返回硬编码计划行。 |
| 已认证导入解析与去重 | P0 | `tests/test_tax_certified_import_service.py`、`tests/test_tax_offset_api.py` | covered | 文件解析、行级状态、唯一键 fallback、重复导入幂等。 |
| 已认证 preview/confirm/job polling API | P0 | `tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/TaxApi.test.ts` | covered | preview 权限、confirm 幂等、job payload contract、modal queued/running/completed；前端 confirm/job 成功后等待当前月份 `tax_offset` operation barrier，再刷新页面数据。 |
| 权限 | P0 | `tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts`、`web/e2e/tax-offset-flow.spec.ts` | covered | read endpoint 访问控制、preview/save 写权限、只读用户隐藏导入/保存；Browser 覆盖 read-export 可读不可写、forbidden/expired 零 tax protected API 和 admin 写入口可见。 |
| 计划保存/idempotency/version conflict | P0 | `tests/test_tax_offset_api.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts` | covered | 保存使用 read model scope/source versions，重复请求幂等，stale source 返回 conflict；Vitest 锁定保存成功后必须先等 `tax_offset` operation barrier，再重新读取 `/api/tax-offset`；Browser 覆盖 409 冲突错误可见、不显示保存成功、不刷新成伪成功且保存按钮可恢复。 |
| API shape 与 metric | P1 | `tests/test_tax_offset_api.py`、`web/src/test/TaxApi.test.ts` | covered | month、calculate、summary、plan save、job mapper、structured metric。 |
| read model service scope | P0 | `tests/test_tax_offset_read_model_service.py` | covered | 只允许月份 scope，schema mismatch 丢弃，deep copy，metadata 无 payload。 |
| SQL read model / Redis cache | P0 | `tests/test_tax_offset_sql_runtime.py`、`tests/test_postgres_state_store.py` | covered | SQL rows 优先、Redis hit/miss/timeout、summary 小 payload、Postgres 不回退 runtime snapshot。 |
| refresh worker / all fan-out | P0 | `tests/test_tax_offset_sql_runtime.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py` | covered | `all` 展开月份 shard，refresh 完成 dirty scope，gateway 去重，worker lifecycle 归属。 |
| lifecycle fan-out | P0 | `tests/test_derived_data_lifecycle_service.py`、`tests/test_tax_offset_api.py` | covered | 发票导入、认证导入、规则变更、OA rebuild 等事件刷新 tax offset，不误刷银行导入。 |
| Workbench relation fan-out | P1 | `web/e2e/workbench-relations-tax-offset-fanout.spec.ts`、`docs/modules/workbench-relations/e2e-coverage.md` | covered | Browser 覆盖 Workbench confirm 后重新请求 `/api/tax-offset`，读取 fresh tax offset read model 并展示 relation 影响后的进项计划行。 |
| App Status / registry | P1 | `tests/test_app_status_overview_service.py`、`tests/test_app_status_readiness_backfill.py`、`tests/test_runtime_worker_registry.py` | covered | route/domain registry、read model readiness、`tax-offset` worker 注册与回填。 |
| migration/schema | P1 | `tests/test_postgres_migrations.py`、`tests/test_postgres_state_store.py` | covered | certified import、tax offset plans、read model 表结构和状态存取。 |
| 前端页面交互 | P1 | `web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts` | covered | loading abort、remount reload、只读权限、导入 modal、drag/drop、非 Excel 拒绝、recalculate、save、搜索/排序/筛选、drawer、高亮、empty；Browser e2e 覆盖真实 Chromium 下的 read-export/forbidden/expired/admin 权限细分、试算、保存、409 conflict 不伪成功、modal preview/confirm、页面刷新、保存/导入成功后无保存失败/导入失败/read model 失败残留、390px 窄屏大表搜索/排序/筛选/横向滚动/按钮无遮挡，以及 read model `refreshing` / `stale` / `missing` / `failed` 时不 false-empty、不泄露 stale reason、不允许保存计划伪成功和 `stale -> fresh` 自动恢复。 |
| 真实外部环境 worker drain | P2 | 运维 runbook / staging smoke | documented-risk | 需要真实 Postgres/Redis/RabbitMQ/systemd `tax-offset` worker。 |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用 | `tests/test_tax_offset_service.py`、`tests/test_tax_certified_import_service.py` | 覆盖税额试算、已认证锁定、计划内/外拆分、唯一键匹配、真实导入行归一化。 |
| 2. Service-layer tests | 适用 | `tests/test_tax_offset_read_model_service.py`、`tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`tests/test_postgres_state_store.py` | 覆盖 read model service、计划保存 service、导入 job repository、Postgres 状态边界。 |
| 3. API contract tests | 适用 | `tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`web/src/test/TaxApi.test.ts`、`web/e2e/tax-offset-flow.spec.ts` | 覆盖 `/api/tax-offset`、calculate、summary、plans、certified-import preview/confirm/job/list 的 response shape、权限和错误；Browser 额外保护 session gate 零 protected API 和 plan save 409 conflict 的用户可见错误合同。 |
| 4. Read model/cache/background job tests | 适用 | `tests/test_tax_offset_sql_runtime.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py` | 覆盖 SQL projection、Redis cache、refresh gateway、worker all fan-out、dirty scope、lifecycle fan-out 和 App Status。 |
| 5. Frontend component and interaction tests | 适用 | `web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/TaxApi.test.ts`、`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/workbench-relations-tax-offset-fanout.spec.ts` | 覆盖用户可见 loading/error/empty/权限/导入/保存/搜索/排序/筛选/drawer/job polling，并用真实浏览器覆盖 read-export/forbidden/expired/admin 权限细分、StrictMode 下 modal confirm 后关闭与刷新、plan save 409 conflict 不伪成功、保存/导入成功后无错误残留、read model 非 fresh gate、390px 窄屏大表滚动和筛选弹层视口定位，以及 Workbench relation 后税金页 fresh 重读。 |
| 6. End-to-end business-flow integration tests | 适用 | `tests/test_tax_offset_api.py`、`tests/test_import_job_queue.py`、`tests/test_tax_offset_sql_runtime.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts`、`web/e2e/workbench-relations-tax-offset-fanout.spec.ts` | 覆盖认证导入 preview -> confirm/job -> read model invalidation -> 页面刷新；Browser e2e 覆盖用户从试算/保存到认证导入刷新后的可见结果、保存/认证导入成功后无错误残留、plan save conflict 防假成功、tax offset read model `stale -> fresh` 自动恢复，也覆盖 Workbench confirm -> tax offset fresh read model -> relation 影响行展示；真实 worker drain 仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用 | 上述全部 tax offset tests，加 invoice lifecycle、pending invoice、ETC、workbench、cost statistics tests 的按改动选择扩展集 | 发票、ETC、关系、规则和 read model 改动都可能影响税金抵扣旧功能；`web/e2e/tax-offset-flow.spec.ts` 保护 read model 非 fresh 不 false-empty/不保存伪成功、plan save conflict 不伪成功、已认证导入 modal 的 StrictMode mounted guard 回归，`web/e2e/workbench-relations-tax-offset-fanout.spec.ts` 保护 relation fan-out 不丢。 |

## 历史 bug 回归库

| 日期 | Bug / 风险 | 回归测试 | 状态 |
| --- | --- | --- | --- |
| 长期 | 没有真实导入数据时，税金抵扣返回硬编码已认证或计划行。 | `tests/test_tax_offset_api.py::test_get_tax_offset_returns_month_rows_without_hardcoded_certified_items_by_default`、`tests/test_tax_offset_service.py::test_month_payload_is_empty_without_real_imports_or_explicit_month_data` | covered |
| 长期 | 已认证记录重复导入造成重复抵扣或重复显示。 | `tests/test_tax_certified_import_service.py::test_confirm_session_persists_month_records_and_deduplicates_reimport`、`tests/test_tax_offset_api.py::test_tax_certified_confirm_is_idempotent_for_same_session` | covered |
| 长期 | 已认证进项被用户再次作为未认证计划行选择，导致重复抵扣。 | `tests/test_tax_offset_service.py::test_month_payload_uses_real_certified_records_to_lock_matching_plan_and_split_outside_plan`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 长期 | API miss/stale 在请求线程同步 rebuild 并伪装 fresh。 | `tests/test_tax_offset_sql_runtime.py` | covered |
| 长期 | `all` refresh 被当作普通 tax offset 月份 payload。 | `tests/test_tax_offset_sql_runtime.py::test_tax_offset_refresh_handler_expands_all_into_month_shards` | covered |
| 长期 | 保存税金抵扣计划时没有校验 read model source version，导致基于旧数据保存。 | `tests/test_tax_offset_api.py::test_tax_offset_plan_save_rejects_stale_source_versions`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 长期 | 税金认证导入确认后页面不刷新税金 read model。 | `tests/test_tax_offset_api.py::test_tax_certified_confirm_invalidates_tax_offset_month_cache`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 长期 | 银行流水导入误刷新税金抵扣。 | `tests/test_tax_offset_api.py::test_bank_import_confirm_does_not_invalidate_tax_offset_cache` | covered |
| 2026-06-13 | 税金抵扣从 OA 附件 parser cache/Workbench 临时行读取发票，绕过统一 Invoice repository。 | `tests/test_tax_offset_service.py::test_month_payload_includes_oa_attachment_invoices_by_issue_month`、`tests/test_tax_offset_api.py::test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month` | covered |
| 2026-06-17 | React StrictMode effect replay 后，已认证导入 modal mounted guard 停留为 false，confirm 200 后直接 return，页面不关闭 modal、不刷新 tax offset。 | `web/e2e/tax-offset-flow.spec.ts` | covered |
| 2026-06-19 | Workbench relation 写入后，税金抵扣页没有重新读取 fresh tax offset read model，导致 relation 影响后的进项计划行不可见或误报读模型错误。 | `web/e2e/workbench-relations-tax-offset-fanout.spec.ts` | covered |
| 2026-06-19 | 税金抵扣页只识别 `refreshing/stale`，`missing/failed/unavailable` read model 可能落入普通空态或允许基于非 fresh 数据保存计划。 | `web/e2e/tax-offset-flow.spec.ts`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 2026-06-19 | 税金抵扣计划保存遇到 source/version conflict 时，页面可能误显示保存成功、刷新成伪成功或吞掉冲突错误。 | `web/e2e/tax-offset-flow.spec.ts`、`tests/test_tax_offset_api.py::test_tax_offset_plan_save_rejects_stale_source_versions` | covered |
| 2026-06-19 | 税金抵扣权限只靠全局 role matrix，可能漏掉本页导入/保存入口、session gate 零 protected API 或 admin 写入口可见性。 | `web/e2e/tax-offset-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts`、`tests/test_tax_offset_api.py` | covered |
| 2026-06-19 | 税金抵扣窄屏下 grid/flex 子项默认 `min-width:auto` 撑宽页面，导致共享横向滚动条失效，筛选弹层也可能被桌面 sidebar inset 推到 viewport 外；后续总 smoke 又发现共享筛选弹层在垂直空间不足时目标 checkbox 位于 viewport 外，已改为根据上下空间定位并让列表内部滚动。 | `web/e2e/tax-offset-flow.spec.ts`、`web/e2e/workbench-large-scroll-flow.spec.ts`、`web/src/test/WorkbenchPaneFilter.test.ts`、`web/src/test/TaxOffsetPage.test.tsx` | covered |
| 2026-06-22 | 计划保存或已认证发票导入成功后立即读取 `/api/tax-offset`，可能读到旧 `tax_offset` read model。 | `web/src/test/TaxOffsetPage.test.tsx::waits for tax offset barrier before reloading after plan save` | covered |

## 关键 smoke flows

1. `发票导入确认 -> invoice_lifecycle refresh -> tax_offset dirty scope -> tax-offset worker -> tax_offset month fresh -> /tax-offset 页面展示`
2. `已认证导入 preview -> 行级状态/计划内外拆分 -> confirm/job queued -> tax_certified_import_confirmed lifecycle -> tax_offset refresh -> 页面 summary 更新`
3. `用户调整计划勾选 -> calculate -> summary 更新 -> save plan with scope/source versions -> tax_offset operation barrier -> stale version conflict 可见且不伪成功，或幂等成功且无保存失败/read model 失败残留`
4. `ETC 发票导入/业务批次变化 -> invoiceFactUpdated / lifecycle -> tax_offset refresh -> 页面重新读取`
5. `pending invoice rules changed -> invoice_lifecycle -> tax_offset + cost_statistics + search refresh -> 不刷新 no_oa_bank_batch/bank_account_balance`
6. `Browser e2e: /tax-offset -> 取消一张进项计划 -> calculate -> 保存计划 -> 页内已认证发票导入 preview/confirm -> 刷新已认证结果 drawer -> 无保存/导入/read model 失败残留`
7. `Browser e2e: /tax-offset -> Workbench confirm relation -> /tax-offset 重新读取 fresh read model -> 显示 relation 影响后的进项计划行`
8. `Browser e2e: /tax-offset -> read model refreshing/stale/missing/failed -> 不显示真实空态/不允许保存计划 -> stale 自动重试到 fresh -> 恢复业务表格`
9. `Browser e2e: /tax-offset -> 修改计划 -> save plan 返回 409 conflict -> 错误可见、不显示保存成功、不刷新成伪成功 -> 保存按钮恢复可用`
10. `Browser e2e: /tax-offset -> read-export 可读无保存/导入入口 -> forbidden/expired 不调用 tax protected API -> admin 可见保存/导入入口`
11. `Browser e2e: /tax-offset -> 390px 窄屏 81/92 行大表 -> 搜索/排序/筛选 -> 共享横向滚动 -> 保存/导入按钮无遮挡`

## 本模块验证命令

最小闭环：

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_service tests.test_tax_certified_import_service tests.test_tax_offset_read_model_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api tests.test_import_job_queue -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v
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

`bash scripts/verify.sh all` 会运行 backend unittest discover、frontend Vitest、frontend build 和 deterministic Playwright smoke，覆盖完整税金抵扣、认证导入、read model、App Status、前端测试集、`web/e2e/tax-offset-flow.spec.ts` 的浏览器权限细分、导入刷新闭环、保存/导入成功后无错误残留、plan save conflict 防假成功、non-fresh read model gate 和窄屏大表交互，以及 `web/e2e/workbench-relations-tax-offset-fanout.spec.ts` 的 Workbench relation -> tax offset fresh read model fan-out。单轮模块验证只跑最小闭环。

## 未测风险

- 本地测试不连接真实税局认证 XLSX 大样本、真实 OA 附件发票缓存或真实 ETC 生产数据；真实数据格式变化需要发布前样本 smoke。
- 本地测试不跑真实 RabbitMQ/Redis/systemd `tax-offset` worker drain；dirty/outbox 到 projection 的真实收敛需要 staging 或夜间 CI/生产前 smoke。
- 前端 Vitest 与 deterministic Playwright 覆盖交互、job polling、真实 Chromium modal confirm/刷新闭环和 non-fresh read model gate；仍不覆盖真实浏览器下载、超大表格性能、真实网络中断恢复和真实税局文件差异。
