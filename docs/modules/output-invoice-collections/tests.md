# 销项发票收款情况 测试矩阵

> 修改本模块前先读取本文件，确认现有测试入口和应覆盖的回归范围。实现后按实际影响更新矩阵。

## 影响面清单

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/OutputInvoiceCollectionsPage.tsx` | rows/filter-options 并行加载、`readModelStatus=refreshing` 自动重试、route unmount cleanup、drawer 状态、admin-only 收据设置 |
| Frontend API mapper | `web/src/features/outputInvoiceCollections/api.ts` | snake_case/camelCase、`read_model_status`、`summary`、`bank.receivedTotal`、receipt/red relation/history/settings shape |
| UI components | `web/src/components/outputInvoiceCollections/*` | 分组表头、筛选菜单、详情 drawer、收款状态 drawer、收据预览/历史 drawer、作废/重开 dialog |
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
| fresh rows/filter/sort/pagination/summary | `tests/test_output_invoice_collection_service.py`、`tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx` | `test_page_size_limit_protects_first_screen_slo` 用 250 行 synthetic 数据验证后端 `page_size=200` 上限和 `page_size>200` 的 `invalid_paging`；前端首屏 rows 请求锁定 `page=1&page_size=20`，每页选项限制为 20/50/100；大数据 SQL EXPLAIN 和浏览器性能仍为真实环境风险 |
| stale/missing/source version mismatch | `tests/test_invoice_usage_collection_sql_runtime.py::test_output_api_stale_returns_refreshing_without_stale_rows` | 真实 worker drain、Redis/RabbitMQ/systemd 需 staging smoke |
| lifecycle overlay | `tests/test_output_invoice_collection_api.py::test_sql_fresh_rows_route_applies_lifecycle_overlay_before_response`、`tests/test_invoice_lifecycle_page_integration.py` | 跨页面最终 UI 展示由下游模块继续补 |
| 手动状态/提醒 | `tests/test_output_invoice_collection_lifecycle.py::test_manual_status_and_reminder_overlay_rows_and_enqueue_month_scope`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | 真实多用户 expectedVersion 冲突未做并发压测 |
| 红蓝票关系 | `tests/test_output_invoice_collection_lifecycle.py::test_red_relation_overlay_adds_manual_evidence`、API route 测试、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | Browser 已覆盖确认红蓝票关系 -> rows refresh -> drawer 已有依据展示；撤销 Browser recovery 和红冲对税金/成本/search 最终展示仍为跨模块 smoke 风险 |
| 正式收据 create/void/reissue/history/settings | `tests/test_output_invoice_collection_lifecycle.py::test_receipts_are_idempotent_and_history_is_real`、`tests/test_output_invoice_collection_lifecycle.py::test_receipt_numbers_are_unique_under_concurrent_creates_and_reset_periods`、`tests/test_postgres_migrations.py::test_output_invoice_receipt_numbering_schema_contract`、`tests/test_output_invoice_collection_api.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | 本地覆盖并发创建、月度/年度/不重置序列、PostgreSQL 唯一约束 contract 和真实 Chromium 创建/历史展示；真实数据库压力与生产历史样本仍需 staging/生产验证 |
| 权限与 admin-only 设置 | `tests/test_output_invoice_collection_api.py::test_detail_routes_require_output_collection_read_session`、前端 admin 设置入口测试 | 全角色矩阵仍由 permissions-and-audit 模块统一审计 |
| 前端 loading/empty/error/refreshing/drawer | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts` | 已覆盖首屏有界 `page_size=20` 请求、20/50/100 页大小选项、refreshing/empty、drawer 和真实 Chromium 状态/收据主流程；视觉回归和超长文本溢出仍需专项浏览器 smoke |
| App Status/readiness/worker registry | `tests/test_app_status_overview_service.py`、`tests/test_runtime_worker_registry.py`、`tests/test_read_model_readiness_reporter.py` | 真实 worker heartbeat/queue backlog 需夜间 CI 或 staging |

## 七类测试适用性

| 类别 | 是否适用 | 当前测试入口 | 说明 |
| --- | --- | --- | --- |
| 1. Business core unit tests | 适用，已覆盖主要规则 | `tests/test_output_invoice_collection_service.py`、`tests/test_invoice_lifecycle_page_integration.py` | 覆盖一张正式销项发票一行、收款状态规则、红冲优先级、receipt preview 规则、非法 filter/sort/relation kind。 |
| 2. Service-layer tests | 适用，已覆盖主要写边界 | `tests/test_output_invoice_collection_lifecycle.py`、`tests/test_output_invoice_collection_service.py` | 覆盖手动状态、提醒、红蓝票关系、receipt 幂等、tenant scoped overlay、enqueue month scope、正式收据并发编号、跨期重置和大页请求上限。 |
| 3. API contract tests | 适用，已覆盖 | `tests/test_output_invoice_collection_api.py` | 覆盖 rows/detail/rules/preview/history/relation routes、structured validation/not found、权限、fresh SQL overlay、lifecycle 写 routes。 |
| 4. Read model/cache/background job tests | 适用，已覆盖核心 read model/worker | `tests/test_invoice_usage_collection_sql_runtime.py`、`tests/test_runtime_worker_registry.py`、`tests/test_app_status_overview_service.py` | 覆盖 output SQL repository native filters/sort、stale 返回 refreshing、不返回 stale rows、source_versions、all scope expansion、RabbitMQ event registration、App Status readiness。 |
| 5. Frontend component and interaction tests | 适用，已覆盖页面主交互 | `web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | 覆盖页面骨架、首屏有界分页请求、空状态、refreshing metadata hidden、retry cleanup、表格、三类 workflow drawer、lifecycle action close、admin-only receipt settings，以及真实 Chromium 中状态/提醒保存、正式收据 drawer 和红蓝票关系 drawer。 |
| 6. End-to-end business-flow integration tests | 适用，已有关键链路级回归 | `tests/test_invoice_lifecycle_page_integration.py`、`tests/test_derived_data_lifecycle_service.py`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | 覆盖 invoice lifecycle 委托、invoice lifecycle 先于下游发票页面、output read model refresh、税金页读取销项发票行，以及真实 Chromium `状态/提醒保存 -> rows refresh -> 正式收据 create/history` 和 `红蓝票关系确认 -> rows refresh -> 已有依据展示`。真实导入到最终页面展示仍为 documented-risk。 |
| 7. Existing feature regression tests | 适用，已覆盖旧行为保护 | `tests/test_output_invoice_collection_*`、`tests/test_invoice_usage_collection_sql_runtime.py`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` | 覆盖旧 API shape、receipt 不伪造历史、stale 不返回旧 rows、页面不暴露 read model metadata、旧导出按钮不被伪造，并防止真实浏览器 drawer 保存/创建收据或红蓝票关系链路断裂。 |

## 历史 bug 回归库

- memory snapshot 为空时必须从 repository output invoice facts 读取：`test_default_rows_read_repository_output_invoice_facts_when_memory_snapshot_is_empty`。
- repository bank reads 必须跨所有 invoice rows batching，避免 N+1/漏读：`test_list_rows_batches_repository_bank_reads_across_all_invoice_rows`。
- filter options 必须基于所有匹配行，不只第一页：`test_filter_options_are_built_from_all_matching_rows_not_first_page_only`。
- 红冲/退款优先于已收/待收规则：`test_collection_status_uses_red_refund_priority_before_collected_and_pending_rules`。
- receipt preview 不允许无收入流水或红冲记录伪造历史：`test_receipt_preview_blocks_no_income_and_red_refund_rows_without_fake_history`。
- receipt preview 多收入流水必须要求选择：`test_receipt_preview_uses_single_income_transaction_or_requires_selection`。
- stale SQL read model 必须返回 `202 refreshing` 且不返回 stale rows：`test_output_api_stale_returns_refreshing_without_stale_rows`。
- fresh SQL rows 返回前必须叠加 lifecycle overlay：`test_sql_fresh_rows_route_applies_lifecycle_overlay_before_response`。
- lifecycle facts 和 receipt history 必须 tenant scoped：`test_lifecycle_overlays_and_receipt_history_are_tenant_scoped`。
- 正式收据必须幂等且历史为真实 facts：`test_receipts_are_idempotent_and_history_is_real`。
- 正式收据编号必须在并发创建下保持唯一，并按 monthly/yearly/none resetPeriod 生成连续序列：`test_receipt_numbers_are_unique_under_concurrent_creates_and_reset_periods`。
- PostgreSQL 正式收据 schema 必须保留 counter scope、receipt_no 和 idempotency 的唯一索引：`test_output_invoice_receipt_numbering_schema_contract`。
- 服务层首屏分页必须拒绝超过 200 的大页请求，且前端首屏必须显式发送有界 `page_size=20`，避免大数据列表退化成全量读取：`test_page_size_limit_protects_first_screen_slo`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`。
- 前端不能把 refreshing payload 当最终空数据，也不能展示 read model 技术细节：`OutputInvoiceCollectionsPage.test.tsx` refreshing/empty 测试。
- 真实浏览器中收款状态/提醒保存必须触发 rows refresh，正式收据创建必须带 idempotency key 并能进入 history 展示：`web/e2e/output-invoice-collections-flow.spec.ts`。
- 真实浏览器中红蓝票关系确认必须触发 rows refresh，重新打开 drawer 后展示人工 relation evidence：`web/e2e/output-invoice-red-relation-fanout.spec.ts`。

## 关键 smoke flows

- 发票导入或关系变化 -> `invoice_lifecycle.read_model.refresh` -> `output_invoice_collection.read_model.refresh` -> `/api/output-invoice-collections/rows` fresh -> 页面展示 `collectionStatus`。
- 手动收款状态/提醒保存 -> lifecycle fact 写入 -> dirty/outbox enqueue `output_invoice_collection` month scope -> rows overlay 更新 -> drawer 关闭并刷新列表。
- Browser e2e：`状态/提醒` drawer 保存手动状态和提醒 -> rows refresh 后显示 `待冲红` -> `待出收据` preview -> 创建正式收据 -> rows refresh 后 `已出收据` history 显示 `SK2026050002`。
- Browser e2e：`红蓝票` drawer 选择红字发票候选 -> 确认人工关系 -> rows refresh 后显示 `待冲红` -> 重新打开 drawer 后显示 `XSFP-E2E-0002 / manual / 浏览器 e2e 红蓝票关系确认`。
- 红蓝票关系确认/撤回 -> relation overlay -> collection status/receipt eligibility 更新 -> 税金抵扣和成本统计通过 invoice lifecycle/domain event/readiness 重新读取。
- 收据 preview -> create formal receipt with idempotency key -> history 展示 issued -> void -> reissue -> history 展示 voided/reissued。
- read model stale/source version mismatch -> API `202 refreshing` -> 前端显示标准 empty/refreshing 行为并自动 retry；不得显示旧 rows 为 fresh。

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

cd web && npx playwright test e2e/output-invoice-collections-flow.spec.ts
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
- 红蓝票关系确认后的本页 rows refresh 和人工依据展示已由 Browser 覆盖；撤销 Browser recovery、税金抵扣、成本统计和搜索最终页面同步仍需跨模块 smoke。
- 浏览器真实大数据表格、长文本、下载/导出和视觉布局仍需人工或专项 Playwright smoke；当前 Browser e2e 只覆盖状态/提醒与正式收据主流程。
- 全角色权限矩阵由 `permissions-and-audit` 模块统一收敛，本模块只覆盖读权限和 admin-only 收据设置入口。
