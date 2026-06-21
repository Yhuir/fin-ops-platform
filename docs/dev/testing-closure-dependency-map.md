# 测试闭环依赖地图

本文是测试闭环的全局依赖地图。它先描述页面、API、read model、worker、domain event 和状态平面之间的关系，再指导各模块在 `docs/modules/<module>/tests.md` 中补齐影响面和测试缺口。

本文件不是产品事实源。业务口径仍以 `docs/product-specs/` 为准；页面和运行时事实仍以 `docs/app-architecture/` 为准；本文件只把这些事实组织成测试闭环视角。

## 分析依据

- 页面注册：`web/src/app/pageRegistry.tsx`
- 页面影响关系：`docs/app-architecture/pages.md`
- 运行时调用链：`docs/app-architecture/runtime-and-ownership.md`
- 前端跨页事件：`web/src/features/domainEvents.ts`
- 后端 HTTP 分发：`backend/src/fin_ops_platform/app/server.py`、`backend/src/fin_ops_platform/app/routes_*.py`
- 派生数据生命周期：`backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`
- Read model freshness：`backend/src/fin_ops_platform/services/read_model_query_gateway.py`
- Read model refresh 入队：`backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- Durable queue：`backend/src/fin_ops_platform/services/runtime_queue.py`
- Worker registry：`backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- App Status domain registry：`backend/src/fin_ops_platform/services/app_status_domain_registry.py`
- App Status read model registry：`backend/src/fin_ops_platform/services/app_status_read_model_registry.py`

## 页面/API/后端 Owner Map

| Module | Route | Page component | API client | 后端入口 | Read model / worker / status | 主要测试入口 |
| --- | --- | --- | --- | --- | --- | --- |
| `reconciliation-workbench` | `/` | `web/src/pages/ReconciliationWorkbenchPage.tsx` | `web/src/features/workbench/api.ts` | `server.py` `/api/workbench*`、`routes_workbench.py` | `workbench`、`workbench_relation`、`workbench-matching`、App Status `workbench` | `tests/test_workbench_*`、`web/src/test/Workbench*.test.tsx` |
| `tax-offset` | `/tax-offset` | `web/src/pages/TaxOffsetPage.tsx` | `web/src/features/tax/api.ts` | `routes_tax.py`、`server.py` `/api/tax-offset*` | `tax_offset`、`invoice_lifecycle`、`cost-tax`、`invoice-lifecycle` | `tests/test_tax_offset_*`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/tax-offset-flow.spec.ts` |
| `cost-statistics` | `/cost-statistics` | `web/src/pages/CostStatisticsPage.tsx` | `web/src/features/cost-statistics/api.ts` | `routes_cost_statistics.py`、`server.py` `/api/cost-statistics*` | `cost_statistics`、`cost-tax` | `tests/test_cost_statistics_*`、`web/src/test/CostStatistics*.test.ts`、`web/e2e/cost-statistics-flow.spec.ts` |
| `bank-details` | `/bank-details` | `web/src/pages/BankDetailsPage.tsx` | `web/src/features/bankDetails/api.ts` | `routes_bank_details.py`、`server.py` `/api/bank-details*` | `bank_detail`、`bank_account_balance`、`bank-detail`、`bank-account-balance` | `tests/test_bank_details_*`、`tests/test_bankdetail_*`、`web/src/test/BankDetails*.test.tsx` |
| `pending-invoices` | `/pending-invoices` | `web/src/pages/PendingInvoicesPage.tsx` | `web/src/features/pendingInvoices/api.ts` | `routes_pending_invoices.py`、`server.py` `/api/pending-invoices*` | `pending_invoice`、`search`、`invoice_lifecycle`、`search-pending`、`invoice-lifecycle` | `tests/test_pending_invoice_*`、`web/src/test/PendingInvoices*.test.tsx` |
| `input-invoice-usage` | `/input-invoice-usage` | `web/src/pages/InputInvoiceUsagePage.tsx` | `web/src/features/inputInvoiceUsage/api.ts` | `server.py` `/api/input-invoice-usage*` | `input_invoice_usage`、`invoice_lifecycle`、`invoice-usage-collection` | `tests/test_input_invoice_usage_*`、`tests/test_invoice_usage_collection_*`、`web/src/test/InputInvoiceUsage*.test.tsx`、`web/e2e/input-invoice-usage-flow.spec.ts` |
| `oa-pending-payments` | `/oa-pending-payments` | `web/src/pages/OaPendingPaymentsPage.tsx` | `web/src/features/oaPendingPayments/api.ts` | `routes_oa_pending_payments.py`、`server.py` `/api/oa-pending-payments*` | `oa_pending_payment`、`invoice_lifecycle`、`invoice-usage-collection`、`oa-sync` | `tests/test_oa_pending_payment_*`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/e2e/oa-pending-payments-flow.spec.ts` |
| `output-invoice-collections` | `/output-invoice-collections` | `web/src/pages/OutputInvoiceCollectionsPage.tsx` | `web/src/features/outputInvoiceCollections/api.ts` | `routes_output_invoice_collections.py`、`server.py` `/api/output-invoice-collections*` | `output_invoice_collection`、`invoice_lifecycle`、`invoice-usage-collection` | `tests/test_output_invoice_collection_*`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/e2e/output-invoice-collections-flow.spec.ts`、`web/e2e/output-invoice-red-relation-fanout.spec.ts` |
| `no-oa-bank-batches` | `/no-oa-bank-batches` | `web/src/pages/NoOaBankBatchPage.tsx` | `web/src/features/noOaBankBatches/api.ts` | `routes_no_oa_bank_batches.py`、`server.py` `/api/no-oa-bank-batches*` | `no_oa_bank_batch`、`no-oa-bank-batch` | `tests/test_no_oa_bank_batch_*`、`web/src/test/NoOaBankBatch*.test.tsx`、`web/e2e/no-oa-bank-batches-flow.spec.ts` |
| `batch-accounting` | `/batch-accounting` | `web/src/pages/BatchAccountingPage.tsx` | `web/src/features/batchAccounting/api.ts` | `server.py` `/api/batch-accounting*` | `workbench_relation`、`workbench-relation` | `tests/test_batch_accounting_api.py`、`web/src/test/BatchAccountingPage.test.tsx`、`web/e2e/batch-accounting-flow.spec.ts` |
| `turnover-ledger` | `/turnover-ledger` | `web/src/pages/TurnoverLedgerPage.tsx` | `web/src/features/turnoverLedger/api.ts` | `routes_turnover_ledger.py`、`server.py` `/api/turnover-ledger*` | `turnover_ledger`、`turnover-ledger` | `tests/test_turnover_*`、`web/src/test/TurnoverLedger*.test.tsx`、`web/e2e/turnover-ledger-flow.spec.ts` |
| `etc-tickets` | `/etc-tickets` | `web/src/pages/EtcTicketManagementPage.tsx` | `web/src/features/etc/api.ts` | `routes_etc.py`、`server.py` `/api/etc*` | `import` worker、ETC import/business batch state | `tests/test_etc_*`、`web/src/test/Etc*.test.tsx`、`web/e2e/etc-tickets-flow.spec.ts` |
| `settings` | `/settings` | `web/src/pages/SettingsPage.tsx` | `web/src/features/workbench/api.ts` | `server.py` `/api/workbench/settings*` | `oa-sync`、`settings_refresh`、`oa_identity`、`state_store` | `tests/test_app_settings_service.py`、`tests/test_settings_data_reset_service.py`、`web/src/test/SettingsPage.test.tsx`、`web/e2e/settings-data-reset-flow.spec.ts` |
| `app-health-operations` | `/operations/app-health` | `web/src/pages/AppHealthOperationsPage.tsx` | `web/src/features/appHealth/api.ts`、`web/src/features/appStatus/api.ts` | `server.py` `/api/app-health*`、`/api/operations/app-health-dashboard` | App Status domains、runtime workers、queue、readiness | `tests/test_app_health_*`、`tests/test_app_status_*`、`web/src/test/AppHealth*.test.tsx` |
| `imports-bank-transactions` | `/imports/bank-transactions` | `web/src/pages/imports/ImportBankTransactionsPage.tsx` | `web/src/features/imports/api.ts` | `server.py` import endpoints | `import` worker、`bank_transaction_import`、`import.process.requested` | `tests/test_import_*`、`web/src/test/ImportsApi.test.ts`、`web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-bank-transactions-flow.spec.ts` |
| `imports-invoices` | `/imports/invoices` | `web/src/pages/imports/ImportInvoicesPage.tsx` | `web/src/features/imports/api.ts` | `server.py` import endpoints | `import` worker、`invoice_import`、`import.process.requested` | `tests/test_import_*`、`web/src/test/ImportsApi.test.ts`、`web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-invoices-flow.spec.ts` |
| `imports-etc-invoices` | `/imports/etc-invoices` | `web/src/pages/imports/ImportEtcInvoicesPage.tsx` | `web/src/features/imports/api.ts`、`web/src/features/etc/api.ts` | `server.py` `/api/etc/import*` | `import` worker、`etc_invoice_import` | `tests/test_etc_backend.py`、`tests/test_import_*`、`web/src/test/EtcApi.test.ts`、`web/src/test/ImportCenterPage.test.tsx`、`web/e2e/imports-etc-invoices-flow.spec.ts` |

## 模块细化：cost-statistics

本节记录成本统计的浏览器测试闭环。业务事实源仍以 `docs/product-specs/`、`docs/modules/cost-statistics/`、`docs/dev/api-contracts.md` 和成本统计 read model 文档为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/CostStatisticsPage.tsx` | time/project/bank/expenseType 视图、project scope、范围选择、drilldown、详情 modal、export center 和 read model refreshing/empty/error 状态不能漂移。 |
| Frontend API mapper | `web/src/features/cost-statistics/api.ts` | explorer/export-preview/export/transaction detail 的 query 参数、project scope、read model status、错误 JSON message 和缓存 key 不能漂移。 |
| API/service/read model | `/api/cost-statistics*`、`CostStatisticsService`、`CostStatisticsReadModelService` | project scope、export row-limit、parent/shard readiness、scope normalization 和 worker enqueue 必须保持一致。 |
| Export center | `ExportCenterModal` | preview 与 download 必须携带当前 view/project scope/filter；结构化后端错误必须展示给用户，不得误当文件下载。 |

当前 Browser e2e：

- `web/e2e/cost-statistics-flow.spec.ts`：真实 Chromium 中进入成本统计页，验证 read model `refreshing` / `stale` / `failed` 不显示最终空态或旧数据，`read_export_only` time-view 导出中心可成功触发 download event 且请求/文件字段正确；同时验证按时间首屏，切到按项目并切换 `project_scope=all`，从项目到费用类型再到流水详情下钻，打开导出中心执行 project preview，并断言同步导出行数上限错误能在弹窗内显示；另有 390px 窄屏 120+ 行长字段 smoke，等待 explorer `read_model_status=fresh` 后验证按时间表和项目下钻表均可横向/纵向滚动、右侧列在 viewport 内、导出入口和选择器未被遮挡且无浏览器错误。
- `web/e2e/imports-etc-invoices-flow.spec.ts`：真实 Chromium 中确认 ETC 导入后进入成本统计，等待 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`，并在按项目/流水视图展示 ETC 导入通行成本项目、通行费和服务商，证明 ETC import 子链路不是只停留在导入页 job feedback。
- `web/e2e/no-oa-bank-batches-flow.spec.ts`：真实 Chromium 中 no-OA selected-row submit 后进入成本统计，等待 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`，并在按项目/流水视图展示免 OA 手续费成本项目、费用类型和银行流水字段，证明 no-OA submit 子链路不是只停留在本页 bucket 状态。
- `web/e2e/turnover-ledger-flow.spec.ts`：真实 Chromium 中外部往来 manual closure confirm 后进入成本统计，等待 `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`，并在按项目/流水视图展示外部往来闭环成本项目、费用类型和银行流水字段，证明 turnover closure 子链路不是只停留在周转页闭环 chip 状态。
- `web/e2e/settings-data-reset-flow.spec.ts`：真实 Chromium 中设置页项目标记完成并保存后进入成本统计，等待 active/all `/api/cost-statistics/explorer` 返回 `read_model_status=fresh`，active scope 排除已完成项目，all scope 保留该项目和金额，证明 settings project scope 子链路不是只停留在设置页保存成功反馈。

## 模块细化：input-invoice-usage

本节记录进项发票使用情况的浏览器测试闭环。业务事实源仍以 `docs/product-specs/invoice-lifecycle.md`、`docs/modules/input-invoice-usage/` 和 `docs/dev/api-contracts.md` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/InputInvoiceUsagePage.tsx` | rows/filter-options 并行加载、read model stale/refreshing、筛选/排序/导出、workflow drawer 状态不能互相污染。 |
| OA reverse drawer | `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx` | 候选子集必须重新 preview 并使用刷新后的 hash；草稿创建后只能展示用户可理解的提交确认，不暴露内部 batch 字段。 |
| Frontend API mapper | `web/src/features/inputInvoiceUsage/api.ts` | snake_case/camelCase、preview/draft/manual-status/history shape、错误消息和权限字段不能漂移。 |
| API/service/read model | `/api/input-invoice-usage*`、`InputInvoiceUsageQueryService`、`InputInvoiceUsageOaReverseService` | rows/filter/detail/export fresh gate、OA reverse preview hash、目标申请人 token、submitted history 和 relation command 边界必须保持一致。 |

当前 Browser e2e：

- `web/e2e/input-invoice-usage-flow.spec.ts`：真实 Chromium 中进入进项发票使用情况页，打开 `以发票反提 OA` drawer，取消一张候选发票后创建 OA 草稿，断言子集 preview 请求只携带当前勾选发票，确认 `已提交 OA` 后进入已提交 tab，并验证历史只展示业务字段、不泄漏内部 batch id。

## 模块细化：oa-pending-payments

本节记录 OA 待付款核对的浏览器测试闭环。业务事实源仍以 `docs/product-specs/invoice-lifecycle.md`、`docs/modules/oa-pending-payments/` 和 `docs/dev/api-contracts.md` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/OaPendingPaymentsPage.tsx` | rows/filter-options 并行加载、read model refreshing/empty、搜索、表头筛选、排序、详情 drawer 和规则 drawer 不能漂移。 |
| Grouped table | `web/src/components/oaPendingPayments/OaPendingPaymentsTable.tsx` | OA 主行、支出流水、进项发票、付款状态、金额/方向 chip、空值和 `+N` 关系展开必须稳定。 |
| Frontend API mapper | `web/src/features/oaPendingPayments/api.ts` | rows/filter/detail query 参数、detail target kind、filters JSON encoding、camelCase/snake_case response shape 不能漂移。 |
| API/service/read model | `/api/oa-pending-payments*`、`OaPendingPaymentApiRoutes`、`OaPendingPaymentQueryService`、`OaPendingPaymentReadModelService` | rows/filter/detail fresh gate、非法参数、detail unavailable、read model enqueue 和权限必须保持一致。 |

当前 Browser e2e：

- `web/e2e/oa-pending-payments-flow.spec.ts`：真实 Chromium 中进入 OA 待付款核对页，验证 OA 主行、支付状态、支出流水和进项发票列，执行搜索、支付状态筛选和交易时间排序，打开 OA/支出流水/发票详情抽屉，并打开支出流水无需开票规则抽屉复用 pending invoice rules endpoint。

## 模块细化：tax-offset

本节记录税金抵扣的浏览器测试闭环。业务事实源仍以 `docs/product-specs/invoice-lifecycle.md`、`docs/modules/tax-offset/` 和 `docs/app-architecture/pages.md` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/TaxOffsetPage.tsx` | 试算、保存、认证导入后必须刷新当前月份 payload；read model refreshing/stale/missing/failed/unavailable 不能显示真实空态或允许保存。 |
| Certified import modal | `web/src/components/tax/CertifiedInvoiceImportModal.tsx` | React StrictMode effect replay 后 mounted guard 必须恢复；confirm 返回后必须关闭 modal 并调用页面刷新。 |
| Frontend API mapper | `web/src/features/tax/api.ts` | preview/confirm/job payload、summary amount 和 source_versions shape 不能漂移。 |
| API/read model | `/api/tax-offset*`、`TaxOffsetQueryService`、`TaxOffsetReadModelRefreshService` | miss/stale 必须走 freshness/enqueue；认证导入 confirm 必须 dirty tax offset month。 |

当前 Browser e2e：

- `web/e2e/tax-offset-flow.spec.ts`：真实 Chromium 中进入税金抵扣页，验证 read-export 可读无保存/导入入口、forbidden/expired 零 tax protected API、admin 写入口可见；验证 390px 窄屏 81/92 行大表搜索、排序、筛选、共享横向滚动和按钮无遮挡；验证 `refreshing` / `missing` / `failed` read model 不显示真实空态、不泄露 stale reason、不允许保存计划，验证 `stale -> fresh` 自动重试恢复；同时覆盖取消一张进项计划后触发 calculate，保存计划，409 source/version conflict 错误可见且不显示保存成功/不伪刷新，再在页内 modal 上传认证结果 Excel、preview 行级计划内/外拆分、confirm 后等待 `/api/tax-offset` 刷新，验证已认证进项税额和已认证 drawer 更新。

## 模块细化：turnover-ledger

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的外部往来款调用链。业务事实源仍以 `docs/product-specs/bank-turnover-and-no-oa.md` 和 `docs/modules/turnover-ledger/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/TurnoverLedgerPage.tsx` | `readModelStatus !== "fresh"` 必须禁用确认、撤回、流水选择和 extra 保存；domain event 只能作为刷新提示 |
| Frontend API mapper | `web/src/features/turnoverLedger/api.ts` | snake_case/camelCase、grouped shape、extra、closure、withdraw、blob export shape 不能漂移 |
| Read facade/API routes | `TurnoverLedgerReadFacade`、`TurnoverLedgerApiRoutes` | grouped/legacy flat 兼容、导出、detail/extra contract |
| Query service | `TurnoverLedgerQueryService` | stale/missing SQL read model 不能伪装 fresh；必须 enqueue `api_stale` / `api_miss` |
| Business core | `TurnoverLedgerService`、`TurnoverRelationService`、`TurnoverLedgerExtraService` | deterministic 不是已闭环；人工闭环必须同组、同对方、同语义、一收一支、零差额 |
| Write boundary | `TurnoverLedgerWriteFacade`、`TurnoverLedgerWriteUnitOfWork`、write adapters | stale precondition、idempotency、rollback、dirty/outbox 必须在同一写边界内被保护 |
| Read model worker | `TurnoverLedgerReadModelRefreshService`、`TurnoverLedgerSqlProjectionBuilder` | projection 不得保存半成品；worker 必须 complete dirty scope |
| App Status | `app_status_domain_registry.py`、`app_status_read_model_registry.py`、`runtime_worker_registry.py` | `turnover_ledger` domain 必须绑定 `turnover-ledger` worker 和 `turnover_ledger.read_model.refresh` |

`turnover-ledger` 写入 fan-out：

| 写入动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| tag-selection 保存 | `turnover_ledger.read_model.refresh` | 往来款 |
| bank-row-tags batch | `bank_detail`、`workbench`、`turnover_ledger` refresh | 银行明细、关联台、往来款、成本统计、搜索 |
| relation extra 保存 | `turnover_ledger.read_model.refresh`，前端 `turnoverLedgerExtraUpdated` | 往来款 |
| manual closure confirm | Turnover manual relation + Workbench active pair relation，`turnoverRelationUpdated` / `workbenchRelationUpdated` | 往来款、关联台、成本统计、搜索 |
| withdraw | relation withdrawn + Workbench relation 恢复，`turnoverRelationUpdated` / `workbenchRelationUpdated` | 往来款、关联台、成本统计、搜索 |

当前 Browser e2e：

- `web/e2e/turnover-ledger-flow.spec.ts`：真实 Chromium 中进入外部往来款页，展开同一公司两条真实 flow rows，manual closure confirm 前触发 `turnover_ledger:all` fresh gate 与 grouped reload/rebind，写成功后等待后端 operation barrier，进入成本统计验证 `/api/cost-statistics/explorer` fresh 和闭环成本行，再从“收支闭环” flow row toolbar 撤回并验证 grouped payload 移除闭环 chip。

## 模块细化：no-oa-bank-batches

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的免 OA 流水批量处理调用链。业务事实源仍以 `docs/product-specs/bank-turnover-and-no-oa.md` 和 `docs/modules/no-oa-bank-batches/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/NoOaBankBatchPage.tsx` | stale polling、route unmount cleanup、跨账户选择保护、internal_transfer batch submit、withdraw dialog |
| Frontend API mapper | `web/src/features/noOaBankBatches/api.ts` | snake_case/camelCase、read_model_status、summary categories、detail rows、mutation errors、affected months |
| Route facade | `routes_no_oa_bank_batches.py` | HTTP status、version conflict、actor mapping、partial failure aggregation、unknown batch/error shape |
| Application service | `NoOaBankBatchApplicationService` | read model missing/stale 不同步 rebuild、after_mutation、durable queue enqueue、Workbench scope expansion |
| Business core | `NoOaBankBatchService` | draft/submitted/withdrawn/stale/conflict、internal_transfer pairing、active relation exclusion、legacy relation migration |
| Tag selection | `NoOaBankBatchTagSelectionService` / `AppSettingsService` | tag selection version、inactive selected cleanup、auto-tag rules labels 即时反映 |
| Write target contract | `bankdetail_write_uow.py` + `tests/test_bankdetail_write_uow_contract.py` | no-OA batch + Workbench pair relation + audit + dirty/outbox 同事务目标 |
| Read model worker | `NoOaBankBatchReadModelRefreshService` | stale source version event 不得 rebuild/overwrite；worker 必须 complete dirty scope |
| App Status | `app_status_domain_registry.py`、`app_status_read_model_registry.py`、`runtime_worker_registry.py` | `no_oa_bank_batches` domain 必须绑定 `no-oa-bank-batch` worker 和 `no_oa_bank_batch.read_model.refresh` |

`no-oa-bank-batches` 写入 fan-out：

| 写入动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| tag-selection 保存 | `no_oa_bank_batch.read_model.refresh` | 免 OA |
| submit-selection | `no_oa_bank_batch_changed`、Workbench pair relation、`workbenchRelationUpdated` | 免 OA、关联台、银行明细、成本统计、搜索 |
| internal_transfer confirm-link | no-OA batch submit + `relation_mode=no_oa_bank_batch` | 关联台、免 OA、银行明细、成本统计、搜索 |
| batch withdraw | pair relation cancel + `no_oa_bank_batch_changed`、`workbenchRelationUpdated` | 免 OA、关联台、银行明细、成本统计、搜索 |
| bank auto tag rules changed | `no_oa_bank_batch` all-scope refresh | 免 OA、银行明细相关候选 |

当前 Browser e2e：

- `web/e2e/no-oa-bank-batches-flow.spec.ts`：真实 Chromium 中进入免 OA 流水批量处理页，选择未提交手续费流水，断言 `submit-selection` 请求体和 operation barrier fresh，进入成本统计验证 downstream fresh read model 与免 OA 成本行，回到已提交 bucket 撤回批次并确认撤回请求体，最后进入历史 bucket 验证已撤回只读。

## 模块细化：batch-accounting

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的批量账务调用链。业务事实源仍以 `docs/product-specs/reconciliation-and-workbench.md` 和 `docs/modules/batch-accounting/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/BatchAccountingPage.tsx` | `readModelStatus !== "fresh"` 必须禁用提交/撤回；bucket、年份、搜索、差额说明和选择缓存不能把旧选择带入新事实 |
| Frontend API mapper | `web/src/features/batchAccounting/api.ts` | snake_case/camelCase、`read_model_status`、`relations_by_bank_row_id`、mutation `affected_months` / `version` shape 不能漂移 |
| HTTP routes | `server.py` `/api/batch-accounting*` | GET 必须只读；submit/withdraw 必须映射错误码、actor、audit、lifecycle event |
| Business service | `BatchAccountingService` | 金额不一致说明、active relation 排除、version conflict、合法日常报销 OA 行、历史 collision repair |
| Relation read facade | `WorkbenchRelationReadFacade` | missing/stale/unavailable 不能伪装 fresh；non-fresh 时必须 enqueue refresh 并透出 reason/scope |
| Relation projection | `WorkbenchRelationSqlProjectionBuilder`、`WorkbenchRelationDistributionMapper` | active batch relation、OA invoice snapshot、linked/unlinked rows、source version 和去重 |
| Write target | `WorkbenchPairRelationService` | submit/withdraw 不能产生半写入；撤回只恢复真实 relation snapshot 并保留历史说明，OA invoice `existing_case` 显示归属不能恢复成 active relation |
| Read model worker | `WorkbenchRelationReadModelRefreshService`、`workbench-relation` worker | `workbench_relation.read_model.refresh` 必须可注册、可观测、可重试 |
| App Status | `app_status_domain_registry.py`、`app_status_job_registry.py`、`runtime_worker_registry.py` | `batch_accounting` domain 必须绑定 `workbench_relation` readiness 和 relation refresh job |

`batch-accounting` 写入 fan-out：

| 写入动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| batch submit | Workbench pair relation + `batch_accounting_relation_changed` + `workbench_relation.read_model.refresh`；前端 `workbenchRelationUpdated` | 批量账务、关联台、银行明细、待找发票、进项/销项/OA 待付款、成本统计、搜索 |
| batch withdraw | Workbench relation withdraw + snapshot restore + `batch_accounting_relation_changed` + `workbench_relation.read_model.refresh`；前端 `workbenchRelationUpdated` | 批量账务、关联台、银行明细、待找发票、进项/销项/OA 待付款、成本统计、搜索 |
| legacy collision repair | 显式 service repair / mutation 路径；GET 列表不允许 repair | 批量账务、关联台 relation projection |
| relation read model missing/stale | `WorkbenchRelationReadFacade` enqueue refresh | 批量账务 mutation 禁用、App Status busy/blocked |

当前 Browser e2e：

- `web/e2e/batch-accounting-flow.spec.ts`：真实 Chromium 中选择未提交批量账务银行流水和 OA 行，submit 后等待 `workbench_relation` operation barrier，再重新读取并在 submitted bucket 展示 relation/OA 明细；随后填写撤回原因，withdraw 后等待 barrier 并回到未提交状态。

## 模块细化：imports-bank-transactions

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的银行流水导入调用链。业务事实源仍以 `docs/product-specs/imports-and-etc.md` 和 `docs/modules/imports-bank-transactions/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/imports/ImportBankTransactionsPage.tsx` | 只传 `mode="bank_transaction"`，真实行为都在共享 `ImportWorkflowPage`；共享改动会影响发票/ETC 导入 |
| Shared workflow | `web/src/components/imports/ImportWorkflowPage.tsx` | 银行账户映射加载、每文件选择、preview stale、session restore、job feedback、route unmount cleanup |
| Frontend API mapper | `web/src/features/imports/api.ts` | multipart `file_overrides`、snake_case/camelCase、duplicate groups、skipped rows、`preview_stale` 错误映射 |
| HTTP routes | `server.py` `/imports/files/preview`、`/imports/files/confirm`、`/imports/files/retry`、`/imports/files/sessions/{session_id}`、legacy `/imports/preview`、`/imports/confirm` | files/session API 与 legacy JSON API 并存；confirm 必须防 stale/idempotent |
| File import service | `FileImportService` | 损坏文件 file-level error、模板识别、银行映射冲突、session/file/batch id、selected files confirm |
| Normalization core | `ImportNormalizationService` | 银行流水 identity、账号维度唯一键、原始文本字段、重复/疑似重复、缺失秒级时间 |
| Import processing | `ImportProcessingService` | confirm 后 enqueue Workbench matching、invalidate tax/cost/workbench；job 成功不代表下游 fresh |
| Import worker | `ImportJobRepository`、`ImportJobWorker`、`runtime_worker_handlers.py` | `import.process.requested` small envelope、processor registry、failed processor 不吞错 |
| App Status | `app_status_domain_registry.py`、`app_status_job_registry.py` | `imports_bank_transactions` 绑定 `import` worker 和 `bank_transaction_import`；`import.process.requested` affected domain 当前偏向 invoices，需后续专项校准 |

`imports-bank-transactions` fan-out：

| 动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| file preview | 创建 `FileImportSession`，不应刷新业务 read model | 当前导入页 |
| file confirm queued | `file_import` background job，RabbitMQ 模式下 `import.process.requested` | 导入页、App Status/App Health |
| file confirm processed | import facts 持久化、Workbench matching 入队、`_persist_state_with_workbench_invalidation` | 银行明细、关联台、往来款、成本统计、搜索 |
| bank import lifecycle | `bank_import_confirmed` -> bank balance/detail、workbench、workbench relation、workbench matching、invoice lifecycle、cost、search | 银行明细、关联台、待找发票、成本统计、App Health |
| preview stale | API `409 preview_stale`，前端提示重新预览 | 当前导入页 |

当前 Browser e2e：

- `web/e2e/imports-bank-transactions-flow.spec.ts`：真实 Chromium 中上传两份银行流水 XLSX、选择银行账户、预览 audit/重复项、处理银行账户冲突弹窗、confirm 后触发 `/api/workbench` 刷新，再进入银行明细验证导入流水可见。

## 模块细化：imports-invoices

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的发票导入调用链。业务事实源仍以 `docs/product-specs/imports-and-etc.md`、`docs/product-specs/invoice-lifecycle.md` 和 `docs/modules/imports-invoices/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/imports/ImportInvoicesPage.tsx` | 只传 `mode="invoice"`，共享 `ImportWorkflowPage` 改动会影响银行流水和 ETC 导入 |
| Shared workflow | `web/src/components/imports/ImportWorkflowPage.tsx` | 每文件 `input_invoice` / `output_invoice` 方向、preview stale、重复审计、session restore、job feedback、route unmount cleanup |
| Frontend API mapper | `web/src/features/imports/api.ts` | multipart `file_overrides`、`template_code=invoice_export`、`batch_type`、snake_case/camelCase、`preview_stale` 错误映射 |
| HTTP routes | `server.py` `/imports/files/preview`、`/imports/files/confirm`、`/imports/files/retry`、`/imports/files/sessions/{session_id}`、legacy `/imports/preview`、`/imports/confirm` | files/session API 与 legacy JSON API 并存；confirm 必须防 stale、unknown selected ids 和重复提交 |
| File import service | `FileImportService` | 损坏 Excel file-level error、模板识别、session/file/batch id、selected files confirm、预览审计 |
| Normalization core | `ImportNormalizationService` | input/output invoice identity、占位电子发票号 fallback、弱 fingerprint、ETC canonical merge、source links、tags |
| Import processing | `ImportProcessingService` | confirm 后必须触发发票 lifecycle、workbench matching、tax/cost scope 和 state persistence |
| Derived lifecycle | `DerivedDataLifecycleService` | `invoice_import_confirmed` 必须使 `invoice_lifecycle` 先于待找发票、税金、进项/销项/OA 待付款等下游页面 |
| App Status | `app_status_domain_registry.py`、`app_status_job_registry.py`、`runtime_worker_registry.py` | `imports_invoices` 绑定 `import` worker 和 `invoice_import`；共享 `import.process.requested` envelope 仍需后续专项校准 |

`imports-invoices` fan-out：

| 动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| file preview | 创建 `FileImportSession` 和 `ImportPreviewAuditCounts`，不应刷新业务 read model | 当前导入页 |
| file confirm queued | `file_import` background job，RabbitMQ 模式下 `import.process.requested` | 导入页、App Status/App Health |
| file confirm processed | input/output invoice facts 持久化、source links、duplicate decisions、Workbench matching scope 计算 | 关联台、待找发票、税金抵扣、进项/销项/OA 待付款、成本统计、搜索 |
| invoice import lifecycle | `invoice_import_confirmed` -> workbench、workbench relation、workbench matching、invoice lifecycle、tax offset、tax month cache、cost statistics、search | 关联台、待找发票、税金抵扣、进项发票使用、销项收款、OA 待付款、成本统计、App Health |
| preview stale | API `409 preview_stale`，前端提示重新预览 | 当前导入页 |

当前 Browser e2e：

- `web/e2e/imports-invoices-flow.spec.ts`：真实 Chromium 中上传两份发票 XLSX、分别选择销项/进项方向、预览 audit/重复与需复核文案、confirm 后触发 `/api/workbench` 刷新并清空导入草稿。

## 模块细化：imports-etc-invoices

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的 ETC 发票导入调用链。业务事实源仍以 `docs/product-specs/imports-and-etc.md`、`docs/operations/etc-business-batches.md` 和 `docs/modules/imports-etc-invoices/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/imports/ImportEtcInvoicesPage.tsx` | 只传 `mode="etc_invoice"`，共享 `ImportWorkflowPage` 改动会影响银行流水和发票导入 |
| Shared workflow | `web/src/components/imports/ImportWorkflowPage.tsx` | zip-only 上传、ready task selector、unavailable task reason、preview stale、job feedback、route unmount cleanup |
| Frontend API mapper | `web/src/features/etc/api.ts` | `/api/etc/import/preview` multipart、长超时、`task_id`、snake_case/camelCase、background job payload、stale error 映射 |
| HTTP routes | `server.py` `/api/etc/import/preview`、`/api/etc/import/confirm`、reconciliation task 和 business batch routes | task version/hash 校验、structured error、idempotent job、queue unavailable、legacy import route |
| Reconciliation task service | `EtcReconciliationTaskService` | ready/importing/imported/closed、confirmed item set hash、missing requirements、source files、delete/reopen invalidating preview |
| Zip parser/filter | `etc_document_parsers.py`、`etc_reconciliation_zip_filter.py` | corrupted zip、重复发票、组合金额匹配、多 requirement 分配、非 ETC evidence |
| ETC service | `EtcService` | import session freshness、duplicate/idempotency、attachments、business batch merge、partial success、delete/release |
| Import processing | `ImportProcessingService` | `etc_invoice_import.confirm` 创建/复用 task-scoped business batch、progress、mark imported/failed、保存 ETC metadata/PDF/XML 附件关系并只关联已存在 canonical invoice |
| Derived lifecycle | `DerivedDataLifecycleService`、`runtime_worker_handlers.py` | `etc_import_confirmed` 刷新 Workbench、invoice lifecycle、tax offset、cost statistics、historical ETC repair、search |
| App Status | `app_status_domain_registry.py`、`app_status_job_registry.py`、`runtime_worker_registry.py` | `imports_etc_invoices` 绑定 `import` worker 和 `etc_invoice_import` job；共享 `import.process.requested` envelope 仍需后续专项校准 |

`imports-etc-invoices` fan-out：

| 动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| ready task 查询 | 读取 confirmed reconciliation task，不刷新业务 read model | ETC 导入页 |
| zip preview | `EtcZipFilterPreview` + `EtcImportSession` + audit，不刷新业务 read model | ETC 导入页 |
| confirm queued | `etc_invoice_import` background job，RabbitMQ 模式下 `import.process.requested` | 导入页、App Status/App Health |
| confirm processed | ETC business batch、ETC invoice metadata/附件关系、已存在 canonical invoice 关联、task imported/failed | ETC 票据管理、关联台 summary、税金抵扣、成本统计、search |
| lifecycle refresh | `etc_import_confirmed` -> workbench、invoice lifecycle、tax offset、cost statistics、historical ETC repair、search | 关联台、税金抵扣、成本统计、ETC 票据管理、App Health |
| task/business batch delete | `etc_reconciliation_task_deleted` 或 business batch reset | ETC 票据管理、关联台 summary row、税金/成本、search |
| preview stale | API `409 stale_reconciliation_task_preview` 或 `409 preview_stale`，前端清空 preview | 当前导入页 |

当前 Browser e2e：

- `web/e2e/imports-etc-invoices-flow.spec.ts`：真实 Chromium 中加载 ready ETC 对账任务、选择 task、上传两份 zip、预览 audit/新增/重复/附件补齐/异常项、确认后展示 `etc_invoice_import` background job feedback，并进入 ETC 票据、税金抵扣和成本统计验证 downstream fresh read model 与导入影响行，同时断言没有走通用 `/imports/files/*` 导入端点。

## 模块细化：output-invoice-collections

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的销项发票收款情况调用链。业务事实源仍以 `docs/product-specs/invoice-lifecycle.md`、`docs/dev/api-contracts.md` 和 `docs/modules/output-invoice-collections/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/OutputInvoiceCollectionsPage.tsx` | rows/filter-options 并行加载、`readModelStatus=refreshing` 自动 retry、route unmount cleanup、workflow drawer 状态、admin-only receipt settings |
| Frontend API mapper | `web/src/features/outputInvoiceCollections/api.ts` | snake_case/camelCase、`read_model_status`、summary/bank/receipt/red relation/status rules shape |
| UI components | `web/src/components/outputInvoiceCollections/*` | 分组表格、筛选菜单、详情 drawer、收款状态 drawer、收据预览/历史 drawer、作废/重开 dialog |
| HTTP routes | `OutputInvoiceCollectionApiRoutes` | SQL read model fresh gate、`202 refreshing`、权限 gate、structured error、receipt idempotency |
| Query service | `OutputInvoiceCollectionQueryService` | 销项发票聚合、状态规则、分页/筛选/排序、relation detail、receipt preview fallback |
| Lifecycle write service | `OutputInvoiceCollectionLifecycleService` | 手动状态、提醒、红蓝票关系、expectedVersion、tenant/actor、transaction-bound enqueue |
| Receipt service | `OutputInvoiceCollectionReceiptService` | preview/create/void/reissue/settings、正式收据幂等、状态冲突、真实 history |
| Read model worker | `InvoiceUsageCollectionReadModelRefreshService` | `output_invoice_collection.read_model.refresh`、all scope fan-out、source_versions、dirty scope complete |
| Source versions | `output_invoice_collection_source_versions()` | lifecycle policy、status rules、receipt schema、OA projection sync 变更必须让旧 rows stale |
| App Status | `app_status_domain_registry.py`、`app_status_read_model_registry.py`、`runtime_worker_registry.py` | domain/read model/worker/job 注册不同步会让页面 busy/blocked 状态误判 |

`output-invoice-collections` 写入 fan-out：

| 写入动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| rows read model miss/stale/source version mismatch | `output_invoice_collection.read_model.refresh`，reason `api_miss` / `api_stale` | 销项收款、App Status/App Health |
| 手动收款状态保存/清空 | lifecycle fact + `output_invoice_collection` month scope，reason `lifecycle_status_changed` | 销项收款；通过 invoice lifecycle/readiness 间接影响税金、成本、search 的最终判断 |
| 收款提醒 upsert/cancel | lifecycle fact + `output_invoice_collection` month scope，reason `lifecycle_reminder_changed` / `lifecycle_reminder_cancelled` | 销项收款、App Status/App Health |
| 红蓝票关系 confirm/delete | red relation fact + `output_invoice_collection` month scope，reason `lifecycle_red_relation_changed` / cancelled | 销项收款 rows、红蓝票 relation 字段 export-preview/download、税金抵扣、成本统计、search 的后续 smoke |
| receipt create | formal receipt fact + `output_invoice_collection` month scope，reason `receipt_created` | 销项收款、收据 history、App Status/App Health |
| receipt void/reissue | receipt status fact + `output_invoice_collection` month scope，reason `receipt_voided` / `receipt_reissued` | 销项收款、收据 history、App Status/App Health |
| receipt settings update | receipt settings fact；不直接刷新历史 rows，后续新建 receipt 使用新设置 | 销项收款 admin drawer |
| invoice lifecycle / pending invoice rules / invoice import | 先 `invoice_lifecycle.read_model.refresh`，再 `output_invoice_collection.read_model.refresh` | 销项收款、待找发票、进项使用、OA 待付款、税金、成本、search |

关键回归保护：

- `tests/test_output_invoice_collection_service.py` 保护业务规则、分页/筛选/排序、receipt preview 和非法参数。
- `tests/test_output_invoice_collection_lifecycle.py` 保护手动状态、提醒、红蓝票关系、receipt 幂等和 tenant scoped overlay。
- `tests/test_output_invoice_collection_api.py` 保护 API contract、权限、structured error 和 SQL fresh overlay。
- `tests/test_invoice_usage_collection_sql_runtime.py` 保护 output read model stale -> `202 refreshing`、source_versions、all scope expansion 和 RabbitMQ event registration。
- `web/src/test/OutputInvoiceCollectionsPage.test.tsx` 保护页面骨架、refreshing/empty、retry cleanup、workflow drawers 和 admin-only 设置。
- `web/e2e/output-invoice-collections-flow.spec.ts` 用真实 Chromium 保护销项收款 rows/filter 首屏、收款状态/提醒保存、rows refresh、正式收据 create 和 history 展示。
- `web/e2e/output-invoice-red-relation-fanout.spec.ts` 用真实 Chromium 保护红蓝票关系确认后 rows refresh、manual evidence 展示、relation 字段 export-preview/download、税金抵扣/成本统计下游 fresh read model，以及撤销后行状态恢复。

## 模块细化：etc-tickets

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的 ETC 票据管理调用链。业务事实源仍以 `docs/product-specs/imports-and-etc.md`、`docs/operations/etc-business-batches.md` 和 `docs/modules/etc-tickets/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/EtcTicketManagementPage.tsx` | unsubmitted/submitted tab、业务批次筛选计数、workflow detail、delete dialog、OA 草稿、manual OA status、source file 上传 |
| Frontend API mapper | `web/src/features/etc/api.ts` | business batch envelope、legacy `/api/etc/batches*` fallback、multipart upload、HTML/proxy error、stale preview error |
| Workbench UI | `CandidateGroupGrid` | `etc_invoice_summary` 折叠/展开、open/paired 区显示、已提交删除后 summary 释放和已存在 canonical invoice 可见性 |
| HTTP routes | `server.py` `/api/etc*` | business batch、reconciliation task、legacy batch、import preview/confirm、source files、manual status、delete/reset 的 contract |
| Business service | `EtcService` | 业务批次幂等、状态流转、ETC metadata/附件占用释放、已存在 canonical invoice 关联、历史 batch 迁移、删除 audit |
| Application service | `EtcBusinessBatchApplicationService` | OA 草稿、manual OA status、source file、绑定 task 恢复、Workbench invalidation |
| Reconciliation service | `EtcReconciliationTaskService` | task ready/importing/imported/closed/deleted、source files、version、deleted tombstone、重启 hydrate |
| Import worker | `ImportProcessingService`、runtime import worker | `etc_invoice_import` job、同 session 重试/幂等、后台导入成功后的 business batch 与 ETC metadata/附件关系保存 |
| Workbench projection | `WorkbenchSqlProjectionBuilder`、`WorkbenchPairRelationService` | submitted business batch -> `etc_invoice_summary`、active relation 排除 open summary、delete/reset 不恢复旧二栏 relation |
| Ops tools | cleanup/migration tools | orphan task 清理显式 allowlist、历史迁移 dry-run/execute 不绕过 service 边界 |
| App Status | import worker、Workbench read model、App Health | import job、Workbench dirty/readiness、ETC route/API smoke、Nginx HTML/502 风险 |

`etc-tickets` 写入 fan-out：

| 写入动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| reconciliation task 创建/上传/confirm | task workflow state + source file metadata；对象存储失败不落半写入 | ETC 票据管理、导入页 ready task |
| ETC ZIP preview/confirm | `etc_invoice_import` background job；成功后保存 ETC invoice metadata/PDF/XML、关联已存在 canonical invoice、同步 business batch | ETC 票据管理、导入页、税金抵扣、关联台 summary、App Status/App Health |
| 创建 OA 草稿 | business batch `oa_confirmation_pending` + audit | ETC 票据管理、真实 OA 系统、App Status |
| manual `submitted` | business batch submitted + linked task closed + Workbench dirty；前端 `etcBusinessBatchUpdated` | ETC 票据管理、关联台、税金抵扣、成本统计、search |
| manual `not_submitted` | 释放本地 ETC 发票占用 + audit；前端 `etcBusinessBatchUpdated` | ETC 票据管理、关联台、税金抵扣、成本统计 |
| business batch delete/reset | 本地批次/task/source/import/ETC metadata 清理；submitted summary 释放；可能取消 active relation | ETC 票据管理、关联台、税金抵扣、成本统计、search |
| reconciliation task delete | 若绑定 business batch，委托同一 business batch delete；否则写 deleted tombstone | ETC 票据管理、导入页 ready task |
| 历史迁移 execute | 旧 active relation/ETC 批次转业务批次 + Workbench invalidation | ETC 票据管理、关联台 paired/open 区 |

关键回归保护：

- `tests/test_etc_backend.py` 保护 business batch API、manual OA status、delete/reset、source file、导入确认、旧 route 兼容和 Workbench summary contract。
- `tests/test_etc_reconciliation_service.py` 保护 task 状态机、source file、deleted tombstone、重启 hydrate 和 active import recovery。
- `tests/test_import_service.py`、`tests/test_postgres_core_repository.py`、`tests/test_platform_runtime_boundary_guards.py` 保护 ETC 导入不创建 canonical invoice、已存在 canonical invoice 关联、弱 fingerprint、不重新引入自动检测 worker。
- `tests/test_workbench_sql_runtime.py`、`tests/test_workbench_pair_relation_service.py` 保护 `etc_invoice_summary` 投影、active relation 排除和 delete/reset 关系恢复规则。
- `web/src/test/EtcTicketManagementPage.test.tsx`、`web/src/test/EtcApi.test.ts`、`web/src/test/CandidateGroupGrid.test.tsx` 保护页面交互、API mapper、错误反馈和 Workbench summary 展示。
- `web/e2e/etc-tickets-flow.spec.ts` 用真实 Chromium 保护 ETC 票据管理未提交业务批次首屏、发票明细表、创建 OA 草稿、人工确认已提交和进入已提交 bucket 的可见闭环。

## 模块细化：settings

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的设置模块调用链。业务事实源仍以 `docs/product-specs/platform-settings-health.md`、`docs/operations/data-safety.md` 和 `docs/modules/settings/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend page | `web/src/pages/SettingsPage.tsx` | section 切换、loading/error、admin-only 凭据、数据重置确认、active job reentry |
| Workbench settings modal | `web/src/components/workbench/WorkbenchSettingsModal.tsx` | 关联台内设置入口与设置页共享 API，项目同步/账户映射/重置入口不能漂移 |
| Frontend API mapper | `web/src/features/workbench/api.ts` | settings payload snake_case/camelCase、data reset job、credential payload、密码不入普通 settings save |
| HTTP routes | `server.py` `/api/workbench/settings*` | GET/POST settings、项目 sync/create/delete、data reset、OA credential routes 的权限和 response shape |
| Settings service | `AppSettingsService` | 项目范围、访问控制、银行映射、OA retention/import、OA invoice offset、银行标签、pending invoice 规则、audit/OA role sync |
| Data reset service | `SettingsDataResetService` | protected targets、导入/文件/关联台/read model/dirty scope 清理、OA rebuild、progress、失败不泄密 |
| Credential service | `OaApplicantCredentialService`、repository、`TargetOaApplicantTokenProvider` | admin-only、pgcrypto 加密、列表不解密、目标 OA 登录失败不泄露密码 |
| Derived lifecycle | `DerivedDataLifecycleService`、read model refresh gateway | 设置规则变化必须产生正确 fan-out；data reset 后旧 read model/cache 不能伪装 fresh |
| App Status | app status registries、overview service | reset/job/dirty scope/worker busy 必须在全局状态平面可见 |

`settings` 写入 fan-out：

| 写入动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| pending invoice 规则保存 | `pending_invoice_rules_changed`，income/expense rule version 独立递增 | 待找发票、关联台、发票 lifecycle、进项发票使用、销项收款、OA 待付款、税金、成本、搜索 |
| 银行标签/自动标签保存 | bank tag settings audit、`bank_auto_tag_rules_changed` 或等价 category lifecycle | 银行明细、免 OA、关联台候选、往来款、成本统计、搜索 |
| 项目范围变化 | `project_scope_changed` 或等价 project scope dirty | 成本统计、搜索、关联台项目展示 |
| 访问控制保存 | state store + OA role sync；不经过 read model | 全局页面可见性、写入权限、导出权限、数据重置和运维入口 |
| OA retention/import filters 保存 | state store；后续 OA reset/rebuild/sync 消费 | OA 待付款、进项/销项、税金、成本、关联台 |
| OA 申请人凭据保存/删除 | 独立 credential repository；普通 settings payload 不变 | 进项发票使用 OA 反提草稿、目标 OA 登录/token provider |
| data reset: bank transactions | 清理银行导入、file imports、matching、Workbench overrides/relations/read models/candidate matches/dirty scopes | 银行明细、关联台、免 OA、往来款、成本、搜索、App Status |
| data reset: invoices | 清理发票导入、税金认证、发票相关派生状态 | 待找发票、税金、进项/销项/OA 待付款、成本、关联台、App Status |
| data reset: OA and rebuild | 按 retention cutoff 重建 OA 源，移除含 OA/附件发票的 relation，保留纯银行-发票 relation | OA 待付款、进项/销项、关联台、税金、成本、搜索、App Status |

关键回归保护：

- `tests/test_app_settings_service.py` 保护 settings normalize、访问控制、银行标签、pending invoice 规则版本、历史非法映射、项目同步/手工项目和 OA role sync。
- `tests/test_settings_data_reset_service.py` 保护 data reset protected targets、job API、password gate、OA rebuild、relation 保留/移除和失败不泄密。
- `tests/test_oa_applicant_credentials_*`、`tests/test_target_oa_applicant_token_provider.py` 保护独立凭据事实源、PG 加密、无密码回显和目标 OA token provider。
- `tests/test_derived_data_lifecycle_service.py`、`tests/test_app_status_overview_service.py` 保护 settings fan-out 到 read model/worker/App Status 的共享 contract。
- `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx` 保护设置页、关联台内设置入口、data reset progress/reentry、admin-only 凭据和全局状态提示。
- `web/e2e/settings-data-reset-flow.spec.ts` 保护真实 Chromium 下设置页 data reset：数据重置 section、影响确认、OA 密码复核、job create/polling、完成后 settings reload 和全局成功反馈；同一 spec 也覆盖项目标记完成 -> 保存 settings -> 成本统计 active/all fresh project scope。

## 模块细化：app-health-operations

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的 App Health / App Status 调用链。业务事实源仍以 `docs/product-specs/platform-settings-health.md`、`docs/app-architecture/runtime-and-ownership.md`、`docs/operations/runtime-worker-governance.md` 和 `docs/modules/app-health-operations/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Frontend operations page | `web/src/pages/AppHealthOperationsPage.tsx` | admin-only、只读 dashboard、unknown 不等于 0、refresh failure 后保留旧 payload 并提示 stale |
| Frontend global status | `web/src/components/shell/AppStatusIndicator.tsx`、`AppHealthStatusContext` | 状态必须来自全局 `app_status`；路由切换不改变 icon；admin 才显示运维入口 |
| Frontend API mappers | `web/src/features/appHealth/api.ts`、`web/src/features/appStatus/api.ts` | malformed payload 不得默认 green；SSE/轮询/BroadcastChannel 只传播后端 snapshot |
| HTTP routes | `server.py` `/api/app-health*`、`/api/operations/app-health-dashboard` | auth guard、SSE contract、dashboard cache、admin-only、`app_status` response shape |
| Overview service | `AppStatusOverviewService` | green/yellow/red 优先级、readiness missing、critical failed/unavailable、worker/dependency/job/domain 映射 |
| Runtime repository | `RuntimeMonitoringRepository` | dirty scopes/outbox/workers/readiness/RabbitMQ/API metrics 聚合；runtime unavailable 不能空 green |
| Registries | `app_status_domain_registry.py`、`app_status_read_model_registry.py`、`app_status_job_registry.py`、`app_status_dependency_registry.py`、`runtime_worker_registry.py` | 新页面/read model/worker/job/dependency 漏同步会让全局状态误判 |
| Readiness tools | `app_status_readiness_backfill.py`、runtime queue ops | 只能从真实 projection 计算 readiness；dead letter resolve 必须检查 fresh readiness 和 active dirty scope |

`app-health-operations` 状态 fan-in / fan-out：

| Runtime fact 来源 | App Status 结果 | 受影响体验 |
| --- | --- | --- |
| `read_model.app_status_readiness` fresh | domain ready/fresh | App Status 可 green；页面可把 read model 当 fresh |
| registry read model 缺 readiness | domain missing busy/yellow | 对应页面不能把空 projection 当 ready |
| critical read model failed/unavailable | domain blocked/red | 对应页面提示不可用，App Status 指向 AppHealth |
| `job.read_model_dirty_scopes` pending/processing/stale | domain busy/yellow | 页面展示 refreshing/stale，而不是旧数据 fresh |
| `job.outbox_events` backlog/failed/dead_lettered | domain busy/blocked 或 attention | worker/read model 收敛风险可见 |
| worker heartbeat missing/stale/mismatch | domain busy/blocked | 依赖该 worker 的页面不能假设任务会完成 |
| background job queued/running/attention | overall/domain busy/yellow | 导入、数据重置、ETC 等任务进度出现在全局状态 |
| dependency missing/unavailable | blocked/red 或 degraded | session/OA/Postgres/RabbitMQ/Redis 依赖异常可见 |
| dashboard metrics refresh failure | dashboard stale warning | 运维仍可看上一份 payload，但不能当 fresh 指标 |

关键回归保护：

- `tests/test_app_health_api.py` 保护 `/api/app-health`、SSE、dashboard admin-only、dirty scopes、jobs、dependencies、cache stale after error。
- `tests/test_app_status_overview_service.py` 保护 registry 一致性、状态优先级、readiness missing/failed、worker missing、runtime unavailable 和 API contract。
- `tests/test_runtime_monitoring.py` 保护 queue backlog、failed jobs、stale dirty scopes、RabbitMQ、worker metrics 和 mismatch。
- `tests/test_app_status_readiness_backfill.py`、`tests/test_runtime_queue_ops.py` 保护 readiness 不伪造 fresh、dead letter resolve 前置条件。
- `tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py` 保护 worker manifest、env examples 和 deploy runtime 配置。
- `web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/AppStatusApi.test.ts`、`web/src/test/AppHealthStatusContext.test.tsx`、`web/src/test/AppHealthBroadcast.test.tsx` 保护 dashboard、global icon、mapper、SSE/轮询和跨 tab sync。

## 模块细化：permissions-and-audit

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的权限与审计横切边界。安全事实源仍以 `SECURITY.md`、`docs/product-specs/platform-settings-health.md` 和 `docs/modules/permissions-and-audit/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| OA token/session | `backend/src/fin_ops_platform/app/auth.py`、`web/src/features/session/api.ts` | `Admin-Token` / Authorization bearer、401/403、session timeout、local dev/test auth |
| Access tier | `AccessControlService`、settings access control | denied/read_export_only/full_access/admin、admin 自动 allowed、dynamic provider fallback |
| Frontend session | `SessionContext`、`SessionGate` | loading/forbidden/expired/error/retry、权限 hooks fail-closed |
| API guard | `server.py` read/mutation/admin route helpers | read API 不信前端可见性；write API 查 `can_mutate_data`；admin-only 查 `can_admin_access` |
| UI permissions | 各页面 `useSessionPermissions()` | readonly 隐藏写入，full access 隐藏 admin-only，admin 显示高风险入口 |
| Audit service/UoW | `AuditTrailService`、业务 service/UoW | actor/tenant/action/entity/metadata，业务事实、audit、dirty/outbox 不得半写入 |
| Sensitive data | session/settings/credential/reset/logging | OA token、password、DSN、credential ciphertext、附件正文不能进 response/log/audit |

权限层级影响：

| Access tier | 允许 | 禁止 | 典型测试 |
| --- | --- | --- | --- |
| `denied` | 无 | 业务 API / 页面访问 | `tests/test_auth_guard.py`、`web/src/test/SessionGate.test.tsx` |
| `read_export_only` | 查询、导出 | 写入、导入确认、数据重置、admin 运维 | `tests/test_session_api.py`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts` |
| `full_access` | 普通业务写入 | 账户管理、OA 凭据、数据重置、AppHealth dashboard | `tests/test_oa_applicant_credentials_api.py`、`web/src/test/SettingsPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts` |
| `admin` | 管理账户、OA 凭据、数据重置、AppHealth dashboard | 不能绕过二次确认/密码复核 | `tests/test_settings_data_reset_service.py`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/e2e/permissions-role-matrix.spec.ts` |

`permissions-and-audit` 写入/审计 fan-out：

| 动作 | 权限 / 审计要求 | 受影响旧功能 |
| --- | --- | --- |
| settings access control 保存 | admin-only；admin 自动 allowed；OA role sync | `/api/session/me`、所有页面按钮、导出、数据重置、AppHealth dashboard |
| 业务写入 / 关系确认撤回 | `can_mutate_data`；actor/tenant 取后端 session；audit + dirty/outbox 同事务 | 关联台、待找发票、批量账务、往来款、免 OA、银行明细 |
| 导出 | read_export_only 允许；错误/HTML 不当作文件 | 银行明细、成本、税金、进项/销项、往来款等导出 |
| 数据重置 / OA 凭据 / AppHealth dashboard | admin-only；密码/token 不泄露 | 设置、App Health、进项 OA 反提、所有 read model |
| worker/service 边界 | worker/service 不 import auth，不解析 cookie/header | runtime worker、read model refresh、platform boundary |

关键回归保护：

- `tests/test_auth_guard.py`、`tests/test_session_api.py` 保护 401/403、session payload、tier 判定、settings allowed/readonly/admin、local dev auth。
- `web/src/test/SessionGate.test.tsx`、`web/src/test/SessionApi.test.ts` 保护前端 session bootstrap、cookie Authorization header、超时和 retry。
- `tests/test_audit_service.py`、`tests/test_workbench_auth_context_idempotency.py`、`tests/test_bankdetail_write_uow_contract.py`、`tests/test_turnover_ledger_uow_contract.py` 保护 actor/tenant、audit metadata 和事务原子性。
- `tests/test_settings_data_reset_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_app_health_api.py` 保护 admin-only 高风险接口和敏感数据不泄露。
- `tests/test_tax_offset_api.py`、`tests/test_pending_invoice_api.py`、`tests/test_turnover_ledger_api.py`、`tests/test_bank_auto_tag_rules_api.py` 保护模块写入权限。
- `tests/test_platform_runtime_boundary_guards.py` 保护 service/worker 不依赖 HTTP auth 边界。
- `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx`、`web/src/test/AppHealthOperationsPage.test.tsx`、`web/src/test/AppStatusIndicator.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx` 保护前端权限展示和禁用。
- `web/e2e/permissions-role-matrix.spec.ts` 保护 read_export_only 全页面可读无 mutation API、settings/tax/import/no-OA 高风险写入口禁用、full_access 非 admin 运维拒绝、admin 设置高危区和 AppHealth 可见。

## 模块细化：app-shell-navigation

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的 App Shell 与导航边界。页面架构事实源仍以 `docs/app-architecture/pages.md`、`docs/app-architecture/runtime-and-ownership.md` 和 `docs/modules/app-shell-navigation/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Provider tree | `web/src/app/App.tsx` | session、page session、import draft、background jobs、App Health、MonthProvider 顺序变化会影响所有页面 |
| Route registry | `web/src/app/pageRegistry.tsx` | route/sidebar/preload/pageKey 不一致；新增页面漏同步 App Status/domain docs |
| Route host | `web/src/app/PageRouteHost.tsx` | 旧页面不卸载、未知 route redirect、lazy fallback、route match `end` 语义 |
| Sidebar | `web/src/components/shell/AppSidebar.tsx`、`sidebarItems.ts` | active route 错误、import shortcut 误高亮、compact drawer 点击后不关闭、preload 改变导航 |
| Top bar / compact shell | `web/src/components/shell/AppTopBar.tsx` | 移动端无法打开导航、OA iframe 空间占用异常 |
| Session gate | `web/src/components/auth/SessionGate.tsx`、`SessionContext` | loading/forbidden/expired/error 时业务页面误渲染，retry 不工作 |
| Page runtime | `web/src/contexts/PageRuntimeContext.tsx` | route 切换后旧页面仍响应 domain/window event |
| Page session state | `web/src/contexts/PageSessionStateContext.tsx`、`useFinanceTableSession.ts` | page/state/user scope 泄漏，保存业务 payload，用户切换后旧筛选污染新用户 |
| Global status display | `AppStatusIndicator`、background progress block | 当前 route 不能改写全局 runtime facts；页面局部 loading 不能变成 App Status |

`app-shell-navigation` route / event 影响：

| 动作 | 当前 contract | 受影响旧功能 |
| --- | --- | --- |
| 新增页面 route | 在 `pageRegistry.tsx` 定义 `path/pageKey/component/preload/end/sidebar` | 侧栏分组、App Status domain registry、route 数量测试、页面文档 |
| 切换 route | 旧页面立即 unmount，新页面 mount；返回页面重新加载 | 所有页面 local state、effect cleanup、domain event listener |
| hover/focus/touch sidebar item | 调用对应 `preload()`，失败被吞掉，不改当前 route | lazy chunk 性能、导航稳定性 |
| 点击 compact sidebar link | 关闭移动 drawer 并交给 React Router 导航 | 移动端/OA iframe 导航 |
| session expired | business route 不渲染，清当前用户 page session | 所有页面筛选/分页/选中状态隔离 |
| 前端 finance domain event | 只通知当前 mounted 页面；卸载页面不 replay | Workbench、银行明细、成本、税金、待找发票等跨页刷新提示 |

关键回归保护：

- `web/src/test/PageRouteHost.test.tsx` 保护 route 不被 animation timer gate、旧页面 unmount、本地 state 不保留、未知 path redirect、lazy fallback、registry contract、旧页面 event listener cleanup。
- `web/src/test/AppSidebar.test.tsx` 保护 desktop/collapsed 样式契约、route chunk preload、nested path active、import shortcut inactive、compact drawer close。
- `web/src/test/App.test.tsx` 保护 workbench、tax offset、cost statistics、settings、import、turnover、embedded OA 和 global status 的 shell smoke。
- `web/src/test/SessionGate.test.tsx` 保护 session bootstrap、forbidden、expired、timeout retry。
- `web/src/test/PageSessionStateContext.test.tsx`、`web/src/test/useFinanceTableSession.test.tsx` 保护 page/state/user scope 隔离、TTL/version/validation、storage fallback、table session restore。
- `web/src/test/domainEvents.test.ts` 保护 finance domain event contract 和 BroadcastChannel。

## 模块细化：finance-table-system

本节记录 `2026-06-11` 首轮 CodeGraph 审计后的 Finance Table System 边界。表格专项事实源仍以 `docs/refactor-ui/table_layout_system.md` 和 `docs/modules/finance-table-system/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Shared table shell | `web/src/components/common/FinanceTable.tsx` | HeroUI Table 外壳、min width、scroll container、footer、列/行/cell class contract |
| Shared primitives | `TableCellStack`、`AmountCell`、`FinanceDirectionTag`、`FinanceStatusTag`、`EmptyValue`、`TruncatedCellText` | 金额/方向/状态/空值/长文本展示不一致，列角色对齐被破坏 |
| Shared pagination | `FinanceTablePagination` | page clamp、summary、上一页/下一页 disabled、页码 callback |
| Table session | `useFinanceTableSession`、`PageSessionStateContext` | page/state/user scope 泄漏、columnsVersion 变化后旧 sort/selection 污染新列、滚动恢复异常 |
| Page wrappers | `*Table.tsx`、`*Page.tsx` | 各页面筛选/排序/分页/导出/drawer/read model 状态契约分散，不能只靠共享 primitive 测试 |
| CSS contracts | `web/src/app/styles.css` | 表格密度 token、列角色对齐、tag 尺寸、motion timing 被视觉重构误伤 |
| Export drawers/dialogs | 各页面 export drawer/dialog | 当前 filters/sort/date/view 未带入导出，HTML/JSON 错误被当文件 |

`finance-table-system` 交互 fan-out：

| 改动 | 受影响页面/模块 | 必测行为 |
| --- | --- | --- |
| 改 `FinanceTable` class/role/minWidth/scroll | 银行明细、税金、导入预览、App Health、部分页面表格 | 表格 aria label、列角色、滚动容器、state row、CSS contract |
| 改 shared primitive | 税金、OA 待付款、导入、App Health、使用共享 primitive 的页面 | 金额右对齐、方向/状态 tag tone、空值文案、长文本 tooltip |
| 改 pagination | 银行明细和使用共享分页的后续页面 | summary、边界页、disabled、callback page |
| 改 `useFinanceTableSession` | 表格 session hook 使用方、未来迁移页面 | pagination/sort/selection/scroll restore、columnsVersion reset、user isolation |
| 改页面级 table wrapper | 对应页面模块 | 旧筛选/排序/分页/search/export/drawer/stale/refreshing 行为 |
| 改 export drawer/dialog | 对应 API/页面模块 | preview、download、错误反馈、当前 filters/sort/date/view、权限/stale disabled |

关键回归保护：

- `web/src/test/FinanceTable.test.tsx` 保护共享分页和 shared cell primitives。
- `web/src/test/TableLayoutTokens.test.ts`、`web/src/test/TableAlignmentStyles.test.ts` 保护表格 token、列角色对齐、tag 稳定尺寸和 motion。
- `web/src/test/useFinanceTableSession.test.tsx`、`web/src/test/PageSessionStateContext.test.tsx` 保护轻量表格 session 与 page/user/session storage 边界。
- `web/src/test/BankDetailsPage.test.tsx`、`web/src/test/InputInvoiceUsagePage.test.tsx`、`web/src/test/PendingInvoicesPage.test.tsx`、`web/src/test/OutputInvoiceCollectionsPage.test.tsx`、`web/src/test/TaxOffsetPage.test.tsx`、`web/src/test/OaPendingPaymentsPage.test.tsx`、`web/src/test/CostStatisticsPage.test.tsx`、`web/src/test/TurnoverLedgerPage.test.tsx`、`web/src/test/ImportCenterPage.test.tsx`、`web/src/test/AppHealthOperationsPage.test.tsx` 保护页面级表格行为。

## 模块细化：oa-integration

本节记录 `2026-06-11` 首轮 CodeGraph / 文档 / 测试审计后的 OA 集成边界。外部系统事实源仍以 `docs/architecture/oa-integration.md`、`docs/references/external-systems.md`、`deploy/oa/README.md` 和 `docs/modules/oa-integration/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| OA session / auth | `app/auth.py`、`OAIdentityService`、`AccessControlService`、`web/src/features/session/api.ts` | `Admin-Token`、Authorization、`/api/session/me`、只读/全操作/admin 分层、OA 超时/无权限 |
| OA Mongo adapter | `MongoOAAdapter` | 外部只读、字段变体、断连 read status、backoff、附件发票 identity/cache |
| OA sync / projection | `OAProjectionSyncService`、`PostgresOAProjectionRepository`、`app/worker.py` | sync API 只能 enqueue，worker upsert 后必须 dirty 下游 scope，retention cutoff 不能误删 manual rows |
| OA pending payment | `OaPendingPaymentApiRoutes`、`OaPendingPaymentQueryService` | rows/filter/detail shape、read model missing/stale、权限、发票生命周期状态 |
| OA manual import | `OAManualImportService`、settings OA manual routes | 未完成 OA 单据不可导入、附件刷新失败、marker 删除/导入幂等、Workbench/Search invalidation |
| Applicant credentials | `OaApplicantCredentialService`、Postgres credential repository | admin-only、password 不回显、pgcrypto key、settings response 不泄漏 |
| Target applicant login | `OaLoginClient`、`TargetOaApplicantTokenProvider` | RSA/openssl、HTTP/网络/无效 JSON/无 token 失败不能伪装成功；错误不泄露 password |
| Input invoice OA reverse | `InputInvoiceUsageOaReverseService`、server OA reverse routes | preview hash、version conflict、idempotency、draft failed recovery、人工 submitted/not_submitted、提交历史脱敏 |
| ETC OA actions | `EtcService`、`EtcBusinessBatchApplicationService`、`routes_etc.py` | 本地撤销/删除不得删除真实 OA；不再自动检测 OA 提交；review URL 清洗 |
| OA deploy / role sync | `deploy/oa/*`、`OARoleSyncService` | 同域路径、环境变量、OA 菜单可见性与 app access tier 不一致 |

`oa-integration` fan-out：

| 动作 | Dirty/outbox / event | 受影响页面 |
| --- | --- | --- |
| OA session bootstrap | 无业务 dirty；决定前端和 API 权限 | 所有页面、所有 API、导出/写入按钮 |
| OA sync by month/all | `oa.sync` worker -> Workbench/Search/Pending Invoice/Invoice Lifecycle/OA Pending/input/output/tax/cost scopes | 关联台、OA 待付款、进项使用、销项收款、待找发票、税金、成本、搜索、App Status |
| OA manual import / delete marker | Workbench/Search invalidation，manual import state store | 设置、关联台、搜索、历史 OA 补录 |
| Applicant credential save/delete | 无业务 dirty；影响后续 OA draft 创建 | 设置、进项 OA 反提、ETC OA 草稿 |
| Target applicant login failure | structured error，不写本地成功状态 | 进项发票使用、ETC 票据 |
| Input invoice OA reverse draft/revoke/manual status | input invoice usage read model invalidation、audit | 进项发票使用、OA 待付款/发票生命周期下游、App Status |
| ETC OA draft/manual status/delete | ETC business batch / invoice occupation / summary relation lifecycle | ETC 票据、关联台、税金、成本、搜索 |
| OA role sync | OA role assignment executor | OA 菜单可见性、app 权限、所有页面入口 |

关键回归保护：

- `tests/test_mongo_oa_adapter.py` 保护 OA Mongo 映射、断连、read status/backoff、附件发票 identity/cache。
- `tests/test_oa_projection_sql_runtime.py`、`tests/test_worker_oa_sync.py` 保护 projection repository、sync worker、downstream dirty scopes 和 HTTP sync enqueue。
- `tests/test_oa_applicant_credentials_service.py`、`tests/test_oa_applicant_credentials_api.py`、`tests/test_postgres_oa_applicant_credentials_repository.py` 保护凭据权限、脱敏和持久化。
- `tests/test_target_oa_applicant_token_provider.py` 保护目标申请人登录 RSA、HTTP/network/JSON/token 失败和缺凭据不登录。
- `tests/test_input_invoice_usage_oa_reverse_service.py`、`tests/test_input_invoice_usage_api.py`、`web/src/test/InputInvoiceUsage*.test.tsx` 保护进项 OA 反提状态机和 UI。
- `tests/test_oa_pending_payment_service.py`、`tests/test_oa_pending_payment_api.py`、`web/src/test/OaPendingPaymentsPage.test.tsx` 保护 OA 待付款页面/API。
- `tests/test_oa_manual_import_service.py`、`tests/test_oa_manual_import_api.py`、`web/src/test/SettingsOaManualSearchImportTable.test.tsx` 保护 OA 手动导入。
- `tests/test_etc_backend.py`、`web/src/test/EtcApi.test.ts`、`web/src/test/EtcOaNavigation.test.ts` 保护 ETC OA 草稿与人工确认。
- `tests/test_auth_guard.py`、`tests/test_session_api.py`、`web/src/test/SessionApi.test.ts`、`web/src/test/SessionGate.test.tsx` 保护 OA session 和权限。
- `tests/test_deploy_oa_script.py`、`tests/test_deploy_oa_nginx_config.py`、`tests/test_oa_role_sync_service.py` 保护同域部署和 role sync。

## 模块细化：data-safety-reset

本节记录 `2026-06-11` 首轮 CodeGraph / 文档 / 测试审计后的数据安全与重置边界。数据操作长期事实仍以 `docs/operations/data-safety.md`、`docs/operations/postgresql-runtime.md`、`docs/operations/runtime-worker-governance.md` 和 `docs/modules/data-safety-reset/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Settings UI | `SettingsPage`、`SettingsDataResetDialogs` | 影响确认、当前 OA 密码、cancel/error、progress reentry、admin-only 显示 |
| API contract | `server.py` `/api/workbench/settings/data-reset*` | admin-only、OA 密码校验、supported/protected targets、job create/query/active、并发 409、密码不泄露 |
| Business service | `SettingsDataResetService` | bank/invoice/OA action 删除范围、protected target、state store save、import file delete、OA relation 保留/删除 |
| Background job | `BackgroundJobService` type `settings_data_reset` | active/running/failed/partial/succeeded 状态、result_summary sanitize、App Health attention |
| Derived lifecycle | `settings_reset_completed`、historical ETC repair、Workbench matching rebuild | reset 后旧 read model/cache 不得伪装 fresh；失败必须 partial/failed |
| Backup/export | `tests/test_export_app_mongo.py`、operations runbooks | 本地只覆盖 legacy export 只读/manifest；真实 PostgreSQL PITR、对象存储和 runtime config 需 staging |
| App Status/App Health | `app_health` API、App Status registries、runtime monitoring | reset job、dirty scope、worker readiness 和 dependency failure 必须被全局状态面暴露 |

当前 Browser e2e：

- `web/e2e/settings-data-reset-flow.spec.ts`：真实 Chromium 中以 admin 进入设置页，打开数据重置 section，经影响确认和 OA 密码复核创建 `settings_data_reset` job，等待 job polling 完成后验证 settings reload 与全局成功状态。

`data-safety-reset` fan-out：

| 重置动作 | 删除/清理 | 必须保留 | 受影响页面/状态 |
| --- | --- | --- | --- |
| `reset_bank_transactions` | 银行流水导入、银行相关 workbench/matching/read model 状态、银行导入文件 | 发票事实、OA 源表、app settings、import metadata | 银行明细、关联台、往来款、成本统计、search、App Health |
| `reset_invoices` | 进/销项发票导入、税金认证、发票相关 workbench/matching/read model 状态、发票导入文件 | 银行流水事实、OA 源表、app settings、import metadata | 待找发票、税金、进项使用、销项收款、OA 待付款、成本统计、关联台、App Health |
| `reset_oa_and_rebuild` | OA 衍生 override/relation/read model，随后按保留策略重建 | 纯银行+发票 relation、OA 附件发票缓存、protected targets | OA 待付款、进项使用、关联台、ETC、成本统计、search、App Health |

关键回归入口：

- `tests/test_settings_data_reset_service.py` 保护 reset action、protected targets、密码校验、job contract、并发 409、OA rebuild 和 lifecycle fan-out。
- `tests/test_app_health_api.py`、`tests/test_background_job_service.py` 保护 failed/partial/interrupted/running job 的 App Health attention 和 job policy。
- `tests/test_export_app_mongo.py` 保护 legacy app Mongo export 只读、manifest/NDJSON counts 和不可覆盖 completed export。
- `tests/test_runtime_state_policy.py` 保护 active/attention background jobs 的 runtime mirror policy。
- `web/src/test/SettingsPage.test.tsx`、`web/src/test/WorkbenchSelection.test.tsx` 保护 impact confirmation、OA password、progress reentry、错误和权限隐藏。

## 模块细化：deploy

本节记录 `2026-06-11` 首轮文档 / 测试审计后的部署边界。发布和运行时长期事实仍以 `docs/dev/nightly-ci.md`、`deploy/oa/README.md`、`docs/operations/postgresql-runtime.md`、`docs/operations/runtime-worker-governance.md` 和 `docs/modules/deploy/` 为准。

| 层级 | 当前入口 | 回归风险 |
| --- | --- | --- |
| Nightly CI | `.github/workflows/nightly-ci.yml`、`scripts/verify.sh` | solo 开发漏跑全量后端、前端、browser e2e、build 或 docs，远端门禁失效 |
| Release script | `scripts/deploy_oa.py`、`scripts/deploy-oa.sh` | release layout、storage preflight、helper contract、activation 顺序和 public route smoke 漂移 |
| Deploy control | `deploy/oa/bin/finops-deploy-control.sh` | env/secrets/migrator/drop-in/restart/readiness/cleanup 任一环节出错会影响所有页面 |
| Worker ensure | `deploy/oa/bin/finops-ensure-runtime-workers.sh`、`runtime_worker_manifest` | 新 worker/read model event 未部署，导致页面长期 refreshing/stale |
| Systemd/env/Nginx | `deploy/oa/systemd/*`、`deploy/oa/env/*`、`nginx.fin-ops.conf.example` | secret 错用、路径 fallback、API 被 SPA 吞掉、assets/cache 策略错误 |
| Health/App Status | `/health`、`/health/ready`、App Health dashboard | systemd active 但 release/worker/runtime 未 ready 时误判成功 |

`deploy` fan-out：

| 发布动作 | 影响 | 受影响页面/状态 |
| --- | --- | --- |
| `bash scripts/verify.sh all` | 后端 check/unittest、前端 Vitest/build、deterministic Playwright browser smoke、docs check | 所有模块的自动化门禁 |
| release upload/check-release | release layout、env contract、storage preflight | 发布前阻断错误包 |
| activate/migration | PostgreSQL schema、API/worker Python env、systemd drop-in、frontend dist | 所有 API、worker 和页面 |
| runtime worker ensure | required worker env/systemd/check command/restart | 所有 read model 页面、App Health |
| Nginx/public route smoke | `/fin-ops/`、`/fin-ops-api/`、`/fin-ops/api/` | session、权限、所有前端 API 请求 |
| cleanup releases | release retention、active refs | rollback 能力和磁盘空间 |

关键回归入口：

- `tests/test_nightly_ci.py` 保护 nightly workflow 和 `scripts/verify.sh all` 不漏跑 backend/frontend/browser e2e/docs。
- `tests/test_deploy_oa_script.py` 保护 release script、deploy-control、worker ensure、storage preflight、readiness 和 public route smoke。
- `tests/test_deploy_oa_nginx_config.py` 保护同域 Nginx path、SPA fallback、assets cache 和 API proxy。
- `tests/test_runtime_worker_registry.py`、`tests/test_deploy_runtime_examples.py` 保护 worker registry/env/dispatcher event contract。
- `tests/test_app.py`、`tests/test_app_postgres_mode.py` 保护 `/health/ready` 和 runtime infrastructure contract。

## 写入动作影响图

| 写入动作 | 典型入口 | Lifecycle event / dirty source | 受影响派生域 | 受影响页面 | 回归测试重点 |
| --- | --- | --- | --- | --- | --- |
| 银行流水导入确认 | import API / import worker | `bank_import_confirmed` | bank balance/detail、workbench、workbench relation、workbench matching、invoice lifecycle、cost statistics、search | 银行明细、关联台、待找发票、成本统计、App Health | 导入确认幂等、dirty scope、worker 入队、旧页面不把 stale 当 fresh |
| 发票导入确认 | import API / import worker | `invoice_import_confirmed` | workbench、workbench relation、workbench matching、invoice lifecycle、tax offset、cost statistics、search | 关联台、待找发票、税金抵扣、进项/销项/OA 待付款、成本统计 | API shape、source_versions、invoice lifecycle 先于下游页面 |
| ETC 导入确认 | `/api/etc/import/confirm` | `etc_import_confirmed` | workbench、invoice lifecycle、tax offset、cost statistics、historical ETC repair、search | ETC、关联台、税金、成本 | ETC 汇总行、散票隐藏、历史修复状态、税金/成本刷新 |
| OA 同步/重建 | OA sync worker / manual import | `oa_rebuilt`、`oa_attachment_invoice_cache_updated` | OA adapter cache、workbench、invoice lifecycle、tax/cost/search | 关联台、OA 待付款、进项/销项、税金、成本 | OA 源只读、附件发票 identity、worker readiness |
| 关系确认/撤回 | workbench actions、batch accounting、turnover | `pair_relation_changed`、`batch_accounting_relation_changed`、`turnover_relation_changed` | bank detail、workbench、relation、invoice lifecycle、pending invoice、tax/cost/search | 关联台、银行明细、批量账务、往来款、待找发票、税金、成本 | stale write contract、idempotency、跨页刷新、关系 read model |
| 批量账务提交/撤回 | `/api/batch-accounting/submit`、`/api/batch-accounting/{relation_id}/withdraw` | `batch_accounting_relation_changed` | workbench relation、workbench、invoice lifecycle、pending invoice、cost/search | 批量账务、关联台、银行明细、待找发票、进项/销项/OA 待付款、成本统计、搜索 | relation read model fresh gate、差额说明、撤回恢复、GET 只读 |
| 标签/规则保存 | bank details、pending invoices、turnover | `bank_transaction_category_changed`、`bank_auto_tag_rules_changed`、`pending_invoice_rules_changed` | bank detail、no-OA、workbench/candidates/matching、invoice lifecycle、pending invoice、cost/search、tax | 银行明细、免 OA、关联台、待找发票、成本、税金 | 配置版本、scope 去重、不误伤无关页面 |
| 税金认证导入 | tax offset import | `tax_certified_import_confirmed` | invoice lifecycle、tax offset、tax month cache、search | 税金抵扣、进项使用、App Health | import job、read model freshness、已认证状态 |
| no-OA 批处理 | no-OA API | `no_oa_bank_batch_changed` | no-OA read model、workbench、relation、cost、search | 免 OA、关联台、成本 | 批量提交/撤回、read model stale polling |
| 设置重置 / backfill | settings data reset | `settings_reset_completed`、`startup_stale_scan` | 多数 read model/cache/session cleanup | 所有列表页、App Health | protected targets 不删除、全局 busy/blocked、worker readiness |
| 项目范围变化 | settings/project scope | `project_scope_changed` | cost statistics、search | 成本统计、搜索 | 成本统计 all/month scope、search 刷新 |
| OA 反提草稿/提交确认 | input invoice usage OA reverse | service/API 状态写入，可能影响 invoice usage/OA 关系 | input invoice usage、invoice lifecycle、OA 关系、审计 | 进项发票使用、设置、App Health | 目标申请人凭据、preview stale、外部 OA 失败、提交历史、不泄露内部 id |

## 前端刷新与跨页事件图

`web/src/features/domainEvents.ts` 定义的事件只作为同一浏览器会话内刷新提示，不是事实源。跨页面一致性必须以后端 facts、read model freshness、dirty scopes、worker readiness 为准。

| Event | 主要 emit 来源 | 主要 subscribe/use 来源 | 测试重点 |
| --- | --- | --- | --- |
| `workbenchRelationUpdated` | 关联台、批量账务、免 OA、往来款、待找发票 | 关联台、银行明细、成本统计 | affectedMonths 过滤、inactive 页面不 replay、后端 dirty scope 已存在 |
| `bankTransactionCategoryUpdated` | 银行明细 | 关联台、成本统计、往来款、免 OA | 分类变更触发候选/成本刷新，不替代后端 lifecycle |
| `bankAutoTagRulesUpdated` | 银行明细规则保存/重应用 | 免 OA、银行明细 | 规则版本 stale、no-OA read model 刷新 |
| `turnoverRelationUpdated` | 往来款确认/撤回 | 关联台、成本统计 | workbench relation 与 turnover read model 一致 |
| `turnoverLedgerExtraUpdated` | 往来款 extra 保存 | 当前主要局部消费 | 不应误触发无关 read model |
| `invoiceFactUpdated` | 待找发票、ETC、发票相关动作 | 税金抵扣、成本统计 | invoice lifecycle 下游顺序、税金/成本刷新 |
| `etcBusinessBatchUpdated` | ETC 业务批次 | 税金抵扣、成本统计 | ETC 提交/撤回后下游不 stale |

相关测试入口：`web/src/test/domainEvents.test.ts`、`web/src/test/useActiveFinanceDomainEvent.test.tsx`。

## Read Model / Worker 依赖图

| Read model key | Scope type | Worker | Refresh event | 主要页面/API | 关键风险 |
| --- | --- | --- | --- | --- | --- |
| `workbench` | `workbench` | `workbench` | `workbench.read_model.refresh` | 关联台、搜索、成本间接依赖 | active generation 原子发布，不能读 building/failed 中间态 |
| `workbench_relation` | `workbench_relation` | `workbench-relation` | `workbench_relation.read_model.refresh` | 批量账务、关联台、下游关系 | 非 fresh 时不能把空关系当全部未提交 |
| `bank_detail` | `bank_detail` | `bank-detail` | `bank_detail.read_model.refresh` | 银行明细、免 OA 上游 | 标签规则版本、stale 后台刷新 |
| `bank_account_balance` | `bank_account_balance` | `bank-account-balance` | `bank_account_balance.read_model.refresh` | 银行明细余额 | critical required；不能用 stale 覆盖 fresh total |
| `pending_invoice` | `pending_invoice` | `search-pending` | `pending_invoice.read_model.refresh` | 待找发票 | 规则版本、人工发票、候选刷新 |
| `search` | `search` | `search-pending` | `search.read_model.refresh` | 搜索/候选相关 | 多事件共同写入，避免全局误清 |
| `invoice_lifecycle` | `invoice_lifecycle` | `invoice-lifecycle` | `invoice_lifecycle.read_model.refresh` | 待找发票、税金、进项/销项/OA 待付款 | 必须先于下游发票页面刷新 |
| `input_invoice_usage` | `input_invoice_usage` | `invoice-usage-collection` | `input_invoice_usage.read_model.refresh` | 进项发票使用 | all scope source_versions 聚合、OA reverse 状态 |
| `output_invoice_collection` | `output_invoice_collection` | `invoice-usage-collection` | `output_invoice_collection.read_model.refresh` | 销项收款 | 收款/红冲/提醒状态 shape |
| `oa_pending_payment` | `oa_pending_payment` | `invoice-usage-collection` | `oa_pending_payment.read_model.refresh` | OA 待付款 | OA/bank/invoice 三类 detail shape |
| `cost_statistics` | `cost_statistics` | `cost-tax` | `cost_statistics.read_model.refresh` | 成本统计 | all 父 scope 与 month shard readiness |
| `tax_offset` | `tax_offset` | `cost-tax` | `tax_offset.read_model.refresh` | 税金抵扣 | 已认证发票、ETC、税金缓存 |
| `no_oa_bank_batch` | `no_oa_bank_batch` | `no-oa-bank-batch` | `no_oa_bank_batch.read_model.refresh` | 免 OA 批次 | stale polling、规则版本 |
| `turnover_ledger` | `turnover_ledger` | `turnover-ledger` | `turnover_ledger.read_model.refresh` | 往来款 | 人工闭环、extra、relation stale precondition |

共享测试入口：`tests/test_read_model_freshness.py`、`tests/test_read_model_query_gateway.py`、`tests/test_read_model_refresh_gateway.py`、`tests/test_read_model_readiness_reporter.py`、`tests/test_runtime_worker_read_model_refresh_scopes.py`、`tests/test_runtime_worker_registry.py`、`tests/test_platform_runtime_boundary_guards.py`。

## API Contract 风险图

跨页面回归最常见的 API 字段包括：

- `read_model_status`
- `read_model_stale_reasons`
- `read_model_scope_key` / `read_model_scope_keys`
- `refresh_enqueued`
- `refresh_reason`
- `source_versions`
- `read_model_generated_at`
- `read_model_schema_version`
- `job` / `job_id`
- `version` / `expected_version`
- `affected_months`
- `error` / `message`
- `rows`
- `summary`
- `pagination`

所有 read model 页面 API contract tests 不应只断言 `status_code == 200`。应断言关键字段、fresh/stale/refreshing 分支、权限失败、stale/conflict、外部依赖失败和空结果语义。

## 共享风险热点与测试映射

| 风险热点 | 主要保护层 |
| --- | --- |
| read model fresh/stale/missing 被误判 | read model freshness unit tests、API contract tests、frontend stale/refreshing interaction tests |
| API response shape 被破坏 | API contract tests、frontend API mapper tests |
| dirty scope 漏发或误发 | service-layer tests、DerivedDataLifecycleService tests、worker enqueue tests |
| worker registry/readiness 未同步 | registry boundary tests、App Status overview tests |
| Redis cache 伪造 fresh | ReadModelQueryGateway tests、cache hit/miss tests |
| RabbitMQ 被误当事实源 | platform boundary guard tests、runtime docs |
| 前端 domain event 被误当事实源 | domain event tests、integration tests requiring backend dirty scope |
| 权限/审计绕过 | auth guard tests、API 403 tests、frontend hidden/disabled tests、audit tests |
| 导出字段变化 | export service tests、download/export-preview API tests |
| migration/历史数据兼容 | migration tests、state store contract tests、production dry-run documented risk |
| 外部 OA/Mongo 失败 | adapter/service tests with failure shape, staging smoke documented risk |
| 并发/idempotency/version conflict | service-layer stale/version tests、idempotency tests |
| 页面卸载/重挂载/session state | PageRouteHost/PageSessionState/useActiveFinanceDomainEvent tests |
| App Status 全局状态误判 | app status overview/API/frontend indicator tests |
| 导入预览过期 | import preview audit/API tests |
| 大数据/SQL 性能退化 | API performance metrics tests、SQL runtime tests、release smoke |
| mock 与真实后端契约偏差 | API mapper tests plus backend API contract tests using the same shape |

## 未确认依赖 / 需动态验证

- 本文件当前以静态代码、文档和测试名为依据，尚未逐模块 trace 每个 endpoint 到具体 service/repository。后续模块闭环必须在对应 `docs/modules/<module>/tests.md` 中补充更细的调用链。
- 真实 OA 登录、OA 草稿、生产 PostgreSQL 历史数据、RabbitMQ/Redis 运行状态不能由本地静态分析证明，需要 staging 或生产前 dry-run/smoke。
- `server.py` 仍有 legacy route 分发，动态路径和 helper 调用需要在具体模块闭环中继续用 CodeGraph/rg 校验。
