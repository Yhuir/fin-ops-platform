# 销项发票收款情况 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/OutputInvoiceCollectionsPage.tsx` | rows/filter-options 并行加载、`readModelStatus=refreshing` 自动重试、route unmount cleanup、drawer 状态、admin-only 收据设置 |
| Frontend API mapper | `web/src/features/outputInvoiceCollections/api.ts` | snake_case/camelCase、`read_model_status`、`summary`、`bank.receivedTotal`、receipt/red relation/history/settings shape、export-preview/download 错误解析和文件名 |
| UI components | `web/src/components/outputInvoiceCollections/*` | 分组表头、筛选菜单、详情 drawer、导出 drawer、收款状态 drawer、收据预览/历史 drawer、作废/重开 dialog |
| HTTP routes | `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py` | SQL read model fresh gate、202 refreshing、不伪装 stale rows、权限 gate、structured errors、idempotency key |
| Query service | `OutputInvoiceCollectionQueryService` | 销项发票行聚合、状态规则、分页/筛选/排序、relation detail、receipt preview fallback |
| Lifecycle write service | `OutputInvoiceCollectionLifecycleService` | 手动状态、提醒、红蓝票关系、expectedVersion、tenant/actor、transaction-bound enqueue |
| Receipt service | `OutputInvoiceCollectionReceiptService` | 正式收据 preview/create/void/reissue/settings、幂等、状态冲突、真实 history |
| Read model worker | `InvoiceUsageCollectionReadModelRefreshService` | `output_invoice_collection.read_model.refresh`、all scope fan-out、source_versions、dirty scope complete |
| Source versions | `output_invoice_collection_source_versions()` | lifecycle policy、status rules、receipt schema、OA projection sync 变更必须触发 stale |
| App Status | `app_status_domain_registry.py`、`app_status_read_model_registry.py`、`runtime_worker_registry.py` | domain/read model/worker/job 注册不同步会让页面 busy/blocked 状态误判 |

## 场景覆盖清单

| 场景 | 当前覆盖 | 缺口/风险 |
| --- | --- | --- |
| fresh rows/filter/sort/pagination/summary | `tests/test_output_invoice_collection_service.py`、`tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | `test_page_size_limit_protects_first_screen_slo` 用 250 行 synthetic 数据验证后端 `page_size=200` 上限和 `page_size>200` 的 `invalid_paging`；前端首屏 rows 请求锁定 `page=1&page_size=20`，每页选项限制为 20/50/100；Browser 覆盖 keyword search、发票号码排序、收款状态/发票号码筛选、page-size 切换后的 rows 请求参数和表格结果同步；本轮新增 rows 首屏暂时 503 后错误态空行、普通空态消失、导出禁用和刷新恢复；money/date 组合由 Vitest/API 覆盖，大数据 SQL EXPLAIN 和浏览器性能仍为真实环境风险 |
| stale/missing/source version mismatch / repository unavailable | `tests/test_invoice_usage_collection_sql_runtime.py::test_output_api_stale_returns_refreshing_without_stale_rows`、`tests/test_invoice_usage_collection_sql_runtime.py::test_output_api_requires_sql_repository_in_production_without_live_scan`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | API 覆盖 stale/source mismatch/生产 SQL repository unavailable -> `202 refreshing` 且不返回 stale rows、不 live scan；Vitest/Browser 覆盖页面显示刷新诊断、不显示普通空态、不泄露 stale reason、不展示旧 rows 或写入口。真实 worker drain、Redis/RabbitMQ/systemd 需 infra-smoke/staging。 |
| 统一关系 OA/流水/发票项多项展示 | `tests/test_output_invoice_collection_service.py::test_unified_relation_payload_exposes_multiple_oa_bank_and_output_invoices`、`tests/test_invoice_usage_collection_sql_runtime.py::test_output_repository_save_persists_oa_relation_columns`、`tests/test_invoice_usage_collection_sql_runtime.py::test_output_api_schema_stale_enqueues_refresh_when_unified_relation_fields_missing`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx::shows invoice aggregate with +N entry point for multi output invoice relations` | 覆盖同一统一 relation 下多 OA、多收入流水、多销项发票 summaries，`/relation-details?kind=oa|bank|invoice`，SQL 原生 OA columns，旧 payload 缺 `oa/invoiceRelations` 触发 refreshing，以及前端多销项发票栏显示发票主信息、价税合计和额外项 `+N`。真实 Browser 长表视觉和 relation group 跨行聚合仍需专项 smoke。 |
| lifecycle overlay | `tests/test_output_invoice_collection_api.py::test_sql_fresh_rows_route_applies_lifecycle_overlay_before_response`、`tests/test_invoice_lifecycle_page_integration.py` | 跨页面最终 UI 展示由下游模块继续补 |
| 手动状态/提醒 | `tests/test_output_invoice_collection_lifecycle.py::test_manual_status_and_reminder_overlay_rows_and_enqueue_month_scope`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | Browser 覆盖状态/提醒保存后等待 `output_invoice_collection` barrier 并 rows refresh、`待冲红` 可见和成功后无可见错误残留；同时覆盖 `collection-status` 暂时 503 后错误可见、drawer/草稿保持、reminder 不半提交、rows 不提前刷新并可重试成功；也覆盖 status 已 200 但 `collection-reminder` 暂时 503 后 drawer/提醒草稿保持、rows 不提前刷新、重试只提交 reminder 而不重复提交已保存且未改变的 status payload；真实多用户 expectedVersion 冲突未做并发压测 |
| 红蓝票关系 | `tests/test_output_invoice_collection_lifecycle.py::test_red_relation_overlay_adds_manual_evidence`、API route 测试、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | Browser 已覆盖确认红蓝票关系 -> barrier -> rows refresh -> drawer 已有依据展示，以及确认后导航税金抵扣/成本统计并由下游 fresh read model 展示 relation 影响结果；同一 flow 覆盖撤销人工关系 -> barrier -> rows refresh -> 依据消失并恢复行状态。Vitest 锁定红蓝票确认在 barrier resolve 前不得刷新 rows。确认和撤销两个成功点都会断言页面没有操作失败、同步失败或 read model 失败等错误残留。search 当前没有独立 Browser route，沿用 API/runtime 证据。 |
| 正式收据 create/void/reissue/history/settings | `tests/test_output_invoice_collection_lifecycle.py::test_receipts_are_idempotent_and_history_is_real`、`tests/test_output_invoice_collection_lifecycle.py::test_receipt_numbers_are_unique_under_concurrent_creates_and_reset_periods`、`tests/test_postgres_migrations.py::test_output_invoice_receipt_numbering_schema_contract`、`tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | 本地覆盖并发创建、月度/年度/不重置序列、PostgreSQL 唯一约束 contract 和真实 Chromium 创建/历史/作废/重开展示；Browser 创建、作废、重开和历史成功后检查无可见错误残留，并断言作废/重开 reason POST body、history reload、barrier 和 rows refresh；同时覆盖创建正式收据暂时 503 后 idempotency key 仍发送、预览 drawer/错误/重试入口保持、rows 不提前刷新、history 不伪读，第二次创建成功后才显示已出收据；也覆盖作废/重开暂时 503 后原因弹窗和输入值保持、history/rows 不提前刷新，第二次确认后才更新 history/rows；真实数据库压力与生产历史样本仍需 staging/生产验证 |
| 导出当前筛选 | `tests/test_output_invoice_collection_api.py::test_export_preview_and_download_use_current_filter_without_pagination`、`tests/test_output_invoice_collection_api.py::test_export_rejects_row_count_over_contract_limit`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | API 覆盖 export-preview/export、真实 xlsx、筛选全集、不受分页限制和 row-limit contract；Browser 覆盖 `read_export_only` 可打开导出、download event、文件名、请求不带 `page/page_size`、样例字段、row-limit 错误可见且零下载，也覆盖红蓝票人工关系确认后 export-preview 和下载文件包含 relation 字段、红字发票号、来源和依据。真实大文件性能和生产浏览器保存仍需 staging/专项 smoke。 |
| 权限与 admin-only 设置 | `tests/test_output_invoice_collection_api.py::test_detail_routes_require_output_collection_read_session`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/permissions-role-matrix.spec.ts` | Browser 已覆盖 `read_export_only` 可读/可导出/可看只读规则和收据历史，但不显示状态/提醒、红蓝票、待出收据、收据编号设置、收据作废/重开，且全程零 mutation API；全角色全页面矩阵仍由 permissions-and-audit 模块统一审计。 |
| 前端 loading/empty/error/refreshing/drawer | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | 已覆盖首屏有界 `page_size=20` 请求、20/50/100 页大小选项、真实 Chromium keyword/filter/sort/page-size rows refresh、rows 暂时加载失败时不显示普通空态并禁用导出、刷新后恢复 rows/分页/导出、refreshing 不显示真实空态、不泄露 stale reason、不展示旧 rows、empty、drawer 和真实 Chromium 状态/收据主流程；状态保存暂时失败时 drawer 不关闭、输入保持、保存按钮恢复可用且成功重试后清除错误；收据作废/重开暂时失败时原因弹窗和输入保持，成功后才关闭；视觉回归和超长文本溢出仍需专项浏览器 smoke |
| App Status/readiness/worker registry | `tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_readiness_reporter.py` | 真实 worker heartbeat/queue backlog 需夜间 CI 或 staging |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用，已覆盖主要规则 | `tests/test_output_invoice_collection_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 覆盖一张正式销项发票一行、收款状态规则、红冲优先级、receipt preview 规则、非法 filter/sort/relation kind，以及统一 relation 下多 OA/流水/销项发票 summaries 和候选关系不计已收款。 |
| 2. Service-layer tests | 适用，已覆盖主要写边界 | `tests/test_output_invoice_collection_lifecycle.py`、`tests/test_output_invoice_collection_service.py` | 覆盖手动状态、提醒、红蓝票关系、receipt 幂等、tenant scoped overlay、enqueue month scope、正式收据并发编号、跨期重置、大页请求上限和 output relation details `kind=oa|bank|invoice`。 |
| 3. API contract tests | 适用，已覆盖 | `tests/test_output_invoice_collection_api.py` | 覆盖 rows/detail/rules/preview/history/relation routes、export-preview/export、structured validation/not found、权限、fresh SQL overlay、lifecycle 写 routes、真实 xlsx 和 row-limit contract。 |
| 4. Read model/cache/background job tests | 适用，已覆盖核心 read model/worker | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 覆盖 output SQL repository native filters/sort、stale 返回 refreshing、不返回 stale rows、source_versions、all scope expansion、RabbitMQ event registration、App Status readiness、OA relation native columns 和缺统一关系字段的 schema stale。 |
| 5. Frontend component and interaction tests | 适用，已覆盖页面主交互 | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | 覆盖页面骨架、首屏有界分页请求、keyword/filter/sort/page-size、空状态、rows 临时失败错误态空行/导出禁用/刷新恢复、refreshing 诊断、metadata hidden、retry cleanup、表格、OA/流水/发票多项 `+N` 入口、导出 drawer、三类 workflow drawer、lifecycle action close、admin-only receipt settings，以及真实 Chromium 中 fresh rows 搜索/筛选/排序/page-size 同步、stale read model 不显示旧 rows/普通空态、状态/提醒保存、状态保存暂时失败后的本地错误/草稿保持/零半提交/重试成功、status 成功但 reminder 暂时失败后的本地错误/提醒草稿保持/不重复提交 status/重试成功、正式收据 preview/create/history/void/reissue drawer/dialog、receipt create 暂时失败后的本地错误/预览保持/零伪历史/重试成功、receipt void/reissue 暂时失败后的原因弹窗/输入保持/重试成功、导出 download event/row-limit 错误、红蓝票 relation 字段导出、read-export 零 mutation权限、红蓝票关系 drawer、状态/收据/红蓝票成功后错误残留检查和本地 browser error 捕获。 |
| 6. End-to-end business-flow integration tests | 适用，已有关键链路级回归 | `tests/test_invoice_lifecycle_page_integration.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts`、`tests/test_search_pending_sql_runtime.py` | 覆盖 invoice lifecycle 委托、invoice lifecycle 先于下游发票页面、output read model refresh、税金页读取销项发票行，以及真实 Chromium `状态/提醒保存 -> rows refresh -> 正式收据 create -> rows refresh -> history -> void -> history/rows refresh -> reissue -> history/rows refresh`、`collection-status 暂时失败 -> drawer/草稿保持 -> reminder 不半提交 -> 重试成功 -> rows refresh`、`collection-status 成功但 reminder 暂时失败 -> drawer/提醒草稿保持 -> rows 不提前刷新 -> 重试只提交 reminder -> rows refresh`、`receipt create 暂时失败 -> preview/error 保持 -> rows/history 不伪成功 -> 重试成功 -> rows refresh`、`receipt void/reissue 暂时失败 -> 原因弹窗/输入保持 -> history/rows 不伪成功 -> 重试成功 -> history/rows refresh`、`当前筛选 -> export-preview -> download`、`红蓝票关系确认 -> rows refresh -> relation 字段导出 -> 已有依据展示 -> 税金抵扣/成本统计 fresh read model 展示 relation 影响结果`；成功写节点都会检查无可见错误残留。search 下游目前由 API/runtime 证明，未来有独立 UI 后再补 Browser。 |
| 7. Existing feature regression tests | 适用，已覆盖旧行为保护 | `tests/test_output_invoice_collection_*`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | 覆盖旧 API shape、receipt 不伪造历史、stale 不返回旧 rows、页面不暴露 read model metadata、refreshing 不回退成普通空态、rows 临时失败不伪装正常空态且不能导出、状态保存暂时失败不关 drawer/不丢草稿/不半提交提醒/不提前刷新 rows、status 成功但 reminder 暂时失败不关 drawer/不丢提醒草稿/不提前刷新 rows/重试不重复提交 status、receipt create 暂时失败不关 drawer/不提前刷新 rows/不伪读 history、receipt void/reissue 暂时失败不丢原因/不提前刷新 history/rows、筛选/排序/page-size 不退化为只测固定 mock、真实导出不再是缺失/伪造按钮，并防止真实浏览器 drawer 保存/创建收据、下载、红蓝票关系链路和“成功但报错提示仍显示”断裂。 |

## 历史 bug 回归库

- memory snapshot 为空时必须从 repository output invoice facts 读取：`test_default_rows_read_repository_output_invoice_facts_when_memory_snapshot_is_empty`。
- repository bank reads 必须跨所有 invoice rows batching，避免 N+1/漏读：`test_list_rows_batches_repository_bank_reads_across_all_invoice_rows`。
- filter options 必须基于所有匹配行，不只第一页：`test_filter_options_are_built_from_all_matching_rows_not_first_page_only`。
- 红冲/退款优先于已收/待收规则：`test_collection_status_uses_red_refund_priority_before_collected_and_pending_rules`。
- receipt preview 不允许无收入流水或红冲记录伪造历史：`test_receipt_preview_blocks_no_income_and_red_refund_rows_without_fake_history`。
- 统一关系中的多 OA、多收入流水、多销项发票必须进入 `oa`、`bankTransactions`、`invoiceRelations` summaries，详情接口支持 `kind=oa|bank|invoice`：`test_unified_relation_payload_exposes_multiple_oa_bank_and_output_invoices`。
- 旧 SQL payload 缺少 `oa` 或 `invoiceRelations` 时必须 schema stale 并返回 refreshing，不能把旧 read model 当 fresh：`test_output_api_schema_stale_enqueues_refresh_when_unified_relation_fields_missing`。
- 前端多项销项发票栏必须显示当前行发票主信息、价税合计和额外项 `+N`，点击后按 `kind=invoice` 打开包含全部发票 summaries 的详情：`web/src/test/OutputInvoiceCollectionsPage.test.tsx::shows invoice aggregate with +N entry point for multi output invoice relations`。
- receipt preview 多收入流水必须要求选择：`test_receipt_preview_uses_single_income_transaction_or_requires_selection`。
- stale SQL read model 必须返回 `202 refreshing` 且不返回 stale rows：`test_output_api_stale_returns_refreshing_without_stale_rows`。
- 默认 all scope 不能直接用全局 `workbench_relation:all` expected source versions 约束当前页面聚合；已 fresh 的月份 shard 不应因为 relation all 版本不同而反复入队并长期显示“正在刷新”：`tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_output_api_all_scope_does_not_loop_on_relation_all_versions`。
- 生产 PostgreSQL runtime 下缺少 `output_invoice_collection` SQL read repository 时不能回退旧 `OutputInvoiceCollectionQueryService.list_rows` live scan：`tests/test_invoice_usage_collection_sql_runtime.py::InvoiceUsageCollectionSqlRuntimeTests::test_output_api_requires_sql_repository_in_production_without_live_scan`。
- fresh SQL rows 返回前必须叠加 lifecycle overlay：`test_sql_fresh_rows_route_applies_lifecycle_overlay_before_response`。
- lifecycle facts 和 receipt history 必须 tenant scoped：`test_lifecycle_overlays_and_receipt_history_are_tenant_scoped`。
- 正式收据必须幂等且历史为真实 facts：`test_receipts_are_idempotent_and_history_is_real`。
- 正式收据编号必须在并发创建下保持唯一，并按 monthly/yearly/none resetPeriod 生成连续序列：`test_receipt_numbers_are_unique_under_concurrent_creates_and_reset_periods`。
- PostgreSQL 正式收据 schema 必须保留 counter scope、receipt_no 和 idempotency 的唯一索引：`test_output_invoice_receipt_numbering_schema_contract`。
- 服务层首屏分页必须拒绝超过 200 的大页请求，且前端首屏必须显式发送有界 `page_size=20`，避免大数据列表退化成全量读取：`test_page_size_limit_protects_first_screen_slo`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`。
- 真实浏览器中 keyword search、发票号码排序、收款状态/发票号码筛选和 page-size 切换必须触发 rows 请求，并且表格结果要跟随后端返回同步变化：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中 rows 首屏暂时加载失败时必须显示错误 alert 和错误态空行，不得显示普通空态或允许导出；点击刷新后必须恢复业务行、分页和导出入口：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 前端不能把 refreshing payload 当最终空数据，也不能展示 read model 技术细节；Browser stale contract 下也不能显示旧 rows 或写入口：`OutputInvoiceCollectionsPage.test.tsx` refreshing 测试、`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中收款状态/提醒保存必须触发 rows refresh，正式收据创建必须带 idempotency key，并能继续在 history 中作废、重开且刷新 history/rows；每个成功点都不能残留操作失败、同步失败或 read model 失败等错误提示：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中收款状态保存暂时失败时，必须显示后端错误、保持状态/提醒草稿、保持 drawer 可重试，不得调用 reminder 半提交，不得提前刷新 rows 或伪装 `待冲红`；重试成功后才刷新 rows：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中收款状态已保存成功但提醒保存暂时失败时，必须显示后端错误、保持 drawer 和提醒草稿、不得提前刷新 rows 或伪装 `待冲红`；重试时不得重复提交已保存且未改变的 status payload，reminder 成功后才刷新 rows：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中创建正式收据暂时失败时，必须继续发送 idempotency key、显示后端错误、保持预览 drawer 和创建按钮，不得提前刷新 rows、显示 `已出收据` 或读取伪历史；重试成功后才刷新 rows：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中正式收据作废/重开暂时失败时，必须显示后端错误、保持原因弹窗和用户输入，不得提前刷新 history 或 rows；重试成功后才关闭弹窗并刷新 history/rows：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中导出必须先加载 export-preview，下载请求必须使用当前筛选全集且不带分页，row-limit 错误必须可见且不能触发 download event：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中红蓝票人工关系确认后，导出预览和下载文件必须包含 `红蓝票关系`、`红蓝票来源`、`红蓝票依据`、红字发票号、来源和确认依据，避免 relation 字段在导出链路丢失：`web/e2e/output-invoice-red-relation-fanout.spec.ts`。
- 真实浏览器中 `read_export_only` 用户必须只能读/导出/查看只读规则和收据历史，不能看到状态/提醒、红蓝票、待出收据、收据编号设置、收据作废/重开等写入口，且不能触发任何 mutation API：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中红蓝票关系确认必须触发 rows refresh，重新打开 drawer 后展示人工 relation evidence，且确认/撤销成功后不能残留操作失败、同步失败或 read model 失败等错误提示：`web/e2e/output-invoice-red-relation-fanout.spec.ts`。
- 真实浏览器中销项红蓝票关系确认后，税金抵扣和成本统计必须各自重新读取 fresh read model，并展示 relation 影响后的进项计划行和成本项目/流水：`web/e2e/output-invoice-red-relation-fanout.spec.ts`。

## 关键 smoke flows

- 发票导入或关系变化 -> `invoice_lifecycle.read_model.refresh` -> `output_invoice_collection.read_model.refresh` -> `/api/output-invoice-collections/rows` fresh -> 页面展示 `collectionStatus`。
- 手动收款状态/提醒保存 -> lifecycle fact 写入 -> dirty/outbox enqueue `output_invoice_collection` month scope -> rows overlay 更新 -> drawer 关闭并刷新列表。
- Browser e2e：`状态/提醒` drawer 保存手动状态和提醒 -> rows refresh 后显示 `待冲红` 且无成功后错误残留 -> `待出收据` preview -> 创建正式收据 -> rows refresh 后 `已出收据` history 显示 `SK2026050002` -> 作废并展示作废原因 -> 重开并展示 `SK2026050003`，每个成功点都无错误残留。
- Browser e2e：`状态/提醒` drawer 第一次保存返回 503 -> drawer 和草稿保持、错误可见、reminder endpoint 零调用、rows 不提前刷新 -> 第二次保存成功后才关闭 drawer、刷新 rows 并显示 `待冲红`。
- Browser e2e：`状态/提醒` drawer status 第一次保存成功、reminder 返回 503 -> drawer 和提醒草稿保持、错误可见、rows 不提前刷新、status endpoint 计数不再增加 -> 第二次保存只重试 reminder，成功后才关闭 drawer、刷新 rows 并显示 `待冲红`。
- Browser e2e：`待出收据` preview 第一次创建返回 503 -> idempotency key 已发送、drawer 和预览保持、错误可见、rows/history 不伪成功 -> 第二次创建成功后才关闭 drawer、刷新 rows 并显示 `已出收据`。
- Browser e2e：`已出收据历史` 中作废/重开第一次返回 503 -> 原因弹窗和输入值保持、错误可见、history/rows 不伪成功 -> 第二次确认成功后才关闭弹窗、刷新 history/rows。
- Browser e2e：fresh 首屏 -> keyword search -> 发票号码排序 -> 收款状态/发票号码筛选 -> page-size 切换，每一步都等待 rows response 并断言 URL contract 与可见行同步。
- Browser e2e：rows 首屏暂时 503 -> 错误 alert 和错误态空行可见 -> 普通空态和导出入口不可用 -> 点击刷新 -> rows 200/fresh -> `XSFP-E2E-0001`、分页和导出入口恢复。
- Browser e2e：`筛选内容导出` -> export-preview 展示样例字段 -> download event 生成 `output-invoice-collections.xlsx`；红蓝票人工关系确认后导出样例和下载文件包含 relation 字段；row-limit 错误展示“超过 20000 行”且 `下载导出` 禁用。
- Browser e2e：`read_export_only` -> 页面可读、可打开只读规则/收据历史/导出预览 -> 状态/提醒、红蓝票、待出收据、收据编号设置、收据作废/重开均不可触发 -> mutation API 调用数为 0。
- Browser e2e：`红蓝票` drawer 选择红字发票候选 -> 确认人工关系 -> rows refresh 后显示 `待冲红` 且无成功后错误残留 -> 重新打开 drawer 后显示 `XSFP-E2E-0002 / manual / 浏览器 e2e 红蓝票关系确认` -> 撤销人工关系 -> rows refresh 后依据消失、恢复 `待收款，已收部分款` 且无成功后错误残留。
- 红蓝票关系确认/撤回 -> relation overlay -> collection status/receipt eligibility 更新 -> 导出 relation 字段 -> 税金抵扣和成本统计通过 invoice lifecycle/domain event/readiness 重新读取；search 下游由 API/runtime 证据保护，当前无独立 Browser route。
- 收据 preview -> create formal receipt with idempotency key -> history 展示 issued -> void -> reissue -> history 展示 voided/reissued。
- read model stale/source version mismatch -> API `202 refreshing` -> 前端显示刷新诊断并自动 retry；不得显示旧 rows 为 fresh、不得显示普通空态、不得泄露 stale reason。

## 现有验证命令

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_output_invoice_collection_service.OutputInvoiceCollectionQueryServiceTests.test_page_size_limit_protects_first_screen_slo \
  tests.test_output_invoice_collection_api \
  tests.test_output_invoice_collection_service \
  tests.test_output_invoice_collection_lifecycle \
  tests.test_invoice_usage_collection_sql_runtime \
  tests.test_invoice_lifecycle_page_integration \
  tests.test_derived_data_lifecycle_service \
  tests.test_runtime_worker_registry \
  tests.test_app_status_overview_service \
  -v

PYTHONPATH=backend/src python3 -m unittest \
  tests.test_postgres_migrations.PostgresMigrationSqlTests.test_output_invoice_receipt_numbering_schema_contract \
  -v

cd web && npm test -- --run \
  src/test/OutputInvoiceCollectionsPage.test.tsx \
  src/test/TaxOffsetPage.test.tsx \
  src/test/AppStatusIndicator.test.tsx \
  src/test/domainEvents.test.ts

cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts --project=chromium
cd web && npx playwright test e2e/output-invoice-red-relation-fanout.spec.ts

bash scripts/verify.sh docs
```

## Nightly CI 覆盖

夜间 CI 应包含上述后端和前端模块命令，并包含全局 docs 校验。push/main smoke 可只跑 `tests.test_output_invoice_collection_api`、`tests.test_output_invoice_collection_lifecycle`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` 和 deterministic Playwright `web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts`。

## 未测风险

- 真实生产 PostgreSQL 大数据、历史半迁移和 source version mismatch 全量回放未由本地单元测试证明。
- 本地 synthetic page-size guard 不替代真实 PostgreSQL EXPLAIN、锁等待、浏览器滚动或真实导出下载性能。
- 真实 RabbitMQ/Redis/systemd `invoice-usage-collection` 与 `invoice-lifecycle` worker drain、heartbeat 和 backlog 需要 staging/生产前 smoke。
- 正式收据编号已由本地并发/跨期测试和 PostgreSQL schema contract 保护；真实数据库锁等待、唯一约束冲突恢复和生产历史样本仍需 staging/生产压测验证。
- read model stale/source mismatch 的本地 API/Vitest/Browser contract 已覆盖；真实 PostgreSQL/RabbitMQ/Redis/systemd worker drain 和实际恢复到 fresh 仍需 infra-smoke/staging。
- 红蓝票关系确认/撤销后的本页 rows refresh、人工依据展示/消失、行状态恢复和 relation 字段导出已由 Browser 覆盖；确认后税金抵扣和成本统计 fresh read model 下游展示也已由 Browser 覆盖。search 没有独立前端 route，仍以 API/runtime 证据和未来外层 UI smoke 处理。
- 浏览器真实大数据表格、长文本、下载/导出和视觉布局仍需人工或专项 Playwright smoke；当前 Browser e2e 已覆盖代表性筛选/排序/page-size、状态/提醒、status/reminder 分步失败恢复、正式收据、导出和红蓝票主流程，但不做所有字段组合的 Playwright 笛卡尔覆盖。
- 全角色权限矩阵由 `permissions-and-audit` 模块统一收敛；本模块已覆盖 `read_export_only` 本页写入口零 mutation、读/导出可用和 admin-only 收据设置入口。
