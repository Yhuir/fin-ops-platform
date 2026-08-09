# Phase 27 页面访问 freshness 与写入口覆盖矩阵

> 状态：`planned` 表示未实施，`deployed-validation-pending` 表示代码、本地门禁和 release 激活已完成但最终生产覆盖行尚未闭合，`migrated` 表示对应 production correctness probe 已通过。本文是 Phase 27 覆盖合同，不是生产 runtime registry。
> 最终运行代码 commit `3b44f08ef` 已作为 production release `main-3b44f08e-20260725151318` 激活；migration `0125` 与正式 Workbench rehydrate 已完成。原 Phase 27 的 17-page/15-read-model HTTP matrix 为 52/52，scope contract violation 为 0，System Audit 16/16 pass，所有 slice 已迁移；后续新增的操作历史页已纳入当前页面 registry。3 秒目标只记录为性能 follow-up，不阻塞状态迁移。

## Operation classes

| Class | 事实与返回合同 | Phase 27 目标 | 性能与收敛口径 |
| --- | --- | --- | --- |
| `fact-write` | 写 canonical business fact / relation / state，返回 commit receipt、受影响业务 identity 与 canonical version | 普通命令不等待下游页面重建；当前页面仅按自身命令合同 reconcile，其他页面只在 route 重进/查询变化/手动刷新/明确重试时校验 source version并按 exact scope 收敛 | HTTP commit 与目标页面 exact-scope 首屏分别计时；普通写不得把全页面收敛塞进写请求 |
| `rule-write` | 写规则/设置事实，返回 rule/settings version 与语义上受影响的 scope | 不因“保存规则”默认全历史重建；访问消费者时比较 rule signature，只重算语义受影响的 exact scopes | 保存保持短路径；当前页面在既有有界超时内最终 fresh，超过 3 秒记 `performance_follow_up`；full-history 不伪装成同步完成 |
| `read-like-command` | POST/PUT 仅用于 preview、calculate、candidate lookup、freshness status；不改变 canonical business fact | 不 dirty、不 fan-out、不等待重建 | 按普通查询 SLO；禁止为了 HTTP method 误投 refresh |
| `explicit-batch` | 导入、reapply、reset、repair、批量 task 等明确的长任务，返回 job/session/receipt | 允许 durable queue 与显式 scoped/full-history 工作，但提交/接受必须有界，进度可观测、可重试、可恢复 | acceptance/commit 与全量收敛分开计时；不要求 3 秒内完成全历史，但不允许 stuck 或阻塞普通写/读 |

共同目标合同：PostgreSQL canonical facts 与 durable queue 继续是事实源；Redis 只缓存 fresh payload；RabbitMQ 只 wake up。未访问/hidden/另一个已打开页面不自动发 query 或 rebuild；route 进入/重进、页面查询变化、浏览器手动刷新或明确重试触发该页面 query，fresh gate 比较 expected source/schema/rule versions，只有 mismatch 才 enqueue exact scope。focus/visibility/BFCache/旧业务事件零业务页面 I/O。`workbench` 保留 active-generation 原子发布例外。

## Registered page coverage

本表必须与 `web/src/app/pageRegistry.tsx` 的 19 个 `appPageDefinitions` 双向一致。`none` 表示页面直接读取 canonical/config/session 或只承载 workflow；不表示它需要新建 read model。

| Page key | Route | Query / read-model owner | Writes and Drawer coverage | Access-time target | Probe id |
| --- | --- | --- | --- | --- | --- |
| `reconciliation-workbench` | `/` | `WorkbenchQueryFacade`; `workbench`, `workbench_relation` | relation/exception/cash/settings actions；`DetailDrawer`、`WorkbenchExceptionDrawer` | active generation + v7 complete exact-month proof（relation/control/claim、OA/bank/invoice 跨月成员、ETC、consumed settings）；并发同 scope 只合并 active proof，完成后不缓存；激活时 query，non-fresh 显示 refreshing | `p27-page-workbench` |
| `cost-statistics` | `/cost-statistics` | `CostStatisticsQueryService`; `cost_statistics` | 标签规则 Drawer | parent + requested view/month dependency gate；规则保存只改 rule version | `p27-page-cost` |
| `bank-details` | `/bank-details` | `BankDetailsApplicationService`; `bank_detail`, `bank_account_balance` | 自动标签规则 Drawer、分类确认/人工分类 | requested month 与 all-only balance 分别 proof；不因任意写重建所有页 | `p27-page-bank` |
| `oa-pending-payments` | `/oa-pending-payments` | `OaPendingPaymentReadModelService`; `oa_pending_payment` | 确认写回、关联支出、规则区域 | requested month/all shard set proof | `p27-page-oa-pending` |
| `bank-flow-rule-batches` | `/bank-flow-rule-batches` | `BankFlowRuleBatchApplicationService`; `bank_flow_rule_batch` | 标签 Drawer、submit/withdraw/reset | requested month/all shard set proof | `p27-page-bank-flow-batch` |
| `batch-accounting` | `/batch-accounting` | `WorkbenchRelationReadFacade`; `workbench_relation` | OA 选择 submit/withdraw、标签规则 Drawer | candidate scopes/year bucket bulk proof；标签规则只影响未提交候选的 query-time 过滤 | `p27-page-batch-accounting` |
| `turnover-ledger` | `/turnover-ledger` | `TurnoverLedgerQueryService`; `turnover_ledger` | 标签/extra Drawer、closure/relation writes | requested month/all scope + canonical relation version | `p27-page-turnover` |
| `etc-tickets` | `/etc-tickets` | ETC task/application query services; `none` | 上传、任务、人工核对、业务批次/OA writes | canonical task state query；只有明确批任务进入后台 job | `p27-page-etc` |
| `tax-offset` | `/tax-offset` | `TaxOffsetQueryService`; `tax_offset` | plan、certified import、results Drawer | requested month proof；import 属于 explicit batch | `p27-page-tax` |
| `pending-invoices` | `/pending-invoices` | `PendingInvoiceReadModelService`; `pending_invoice`, `invoice_lifecycle` | 规则/详情/导出/选择发票/关系 Drawer | exact direction/filter/month page scope + lifecycle dependency proof | `p27-page-pending-invoice` |
| `input-invoice-usage` | `/input-invoice-usage` | `InputInvoiceUsageReadModelService`; `input_invoice_usage`, `invoice_lifecycle` | 详情/导出/规则/OA reverse Drawer | requested month shard + relation/lifecycle versions | `p27-page-input-usage` |
| `output-invoice-collections` | `/output-invoice-collections` | `OutputInvoiceCollectionCanonicalQueryService`; `none` | canonical 详情/导出；无业务写 Drawer | canonical output invoices + active formal relations + bank facts direct query；无 read model/lifecycle/receipt gate | `p27-page-output-collection` |
| `settings` | `/settings` | settings/account/OA credential services; `none` | settings、账户、凭据、手工 OA、reset | query canonical settings versions；仅语义消费者按访问验证 | `p27-page-settings` |
| `app-health-operations` | `/operations/app-health` | App Status/runtime queue/audit queries; all 15 status entries | admin ack/retry；页面本身无业务 Drawer rebuild | 只读 current-effective runtime facts；运维命令显式执行 | `p27-page-app-health` |
| `operation-history` | `/operations/history` | `audit.events` canonical append-only query；`none` | 无业务写；详情使用只读 Drawer | admin-only 直接读取上线覆盖点后的审计事实；不触发 read model/queue | `p27-page-operation-history` |
| `imports.bank-transactions` | `/imports/bank-transactions` | import session service; `none` | preview/retry/confirm import | preview read-like；confirm explicit batch，受影响页面访问时精确收敛 | `p27-page-import-bank` |
| `imports.invoices` | `/imports/invoices` | import session service; `none` | preview/retry/confirm import | preview read-like；confirm explicit batch，受影响页面访问时精确收敛 | `p27-page-import-invoice` |
| `imports.etc-invoices` | `/imports/etc-invoices` | import + ETC session services; `none` | preview/retry/confirm import | preview read-like；confirm explicit batch，受影响页面访问时精确收敛 | `p27-page-import-etc` |

## Read model coverage

本表 15 个 key 必须与 `READ_MODEL_MANIFEST` 双向一致。Consumer 只记录正式页面/资源入口，不创建新的依赖 registry。

| Read model key | Scope / all semantics | Query owner | Page or resource consumers | Access-time proof and migration target | Status |
| --- | --- | --- | --- | --- | --- |
| `workbench` | `workbench`; month active generation；`all=active_month_shard_aggregate` | `WorkbenchQueryFacade` | `reconciliation-workbench`, `cost_statistics`, `search` | v7 complete canonical source vector + active generation/current-effective queue；Application shared builder合并重叠proof；migration `0125` 与生产受控rehydrate已完成；保留原子发布例外 | `migrated` |
| `workbench_relation` | `workbench_relation`; month；`all=fan_out_command` | `WorkbenchRelationReadFacade` | `reconciliation-workbench`, `batch-accounting`, invoice family | exact relation scope source versions；消费者不得把旧 relation projection 伪装 fresh | `migrated` |
| `bank_detail` | `bank_detail`; month；`all=fan_out_command` | `BankDetailsApplicationService` | `bank-details`, `pending-invoices`, `cost-statistics` | exact month signature/source versions + queue state | `migrated` |
| `bank_account_balance` | `bank_account_balance`; global `all=queryable_all_scope` | `BankDetailsApplicationService` | `bank-details`, App Status | all-only canonical balance source version | `migrated` |
| `pending_invoice` | `pending_invoice`; `direction:filter_group[:month]`; bare all forbidden | `PendingInvoiceReadModelService` | `pending-invoices`, `invoice_lifecycle` | page-first-screen exact scope + bank/relation dependency versions | `migrated` |
| `search` | `search`; month；`all=fan_out_command` | `Search read API` | global search, settings manual OA search | requested month index source versions；普通写零 refresh，访问 non-fresh 才 enqueue | `migrated` |
| `invoice_lifecycle` | `invoice_lifecycle`; month；`all=fan_out_command` | `InvoiceLifecycleReadFacade` | pending/input/output/OA invoice resources | exact lifecycle + upstream source proof；strict stale consumer | `migrated` |
| `input_invoice_usage` | `input_invoice_usage`; month；`all=fan_out_command` | `InputInvoiceUsageReadModelService` | `input-invoice-usage` | exact month + relation/lifecycle/rule signature | `migrated` |
| `output_invoice_collection` | `output_invoice_collection`; month；`all=fan_out_command` | `OutputInvoiceCollectionReadApplicationService` | `output-invoice-collections` | exact month + relation/lifecycle/receipt/rule versions | `migrated` |
| `oa_pending_payment` | `oa_pending_payment`; month；`all=fan_out_command` | `OaPendingPaymentReadModelService` | `oa-pending-payments`, lifecycle resource | exact OA snapshot/relation/schema versions | `migrated` |
| `cost_statistics` | `cost_statistics`; `active/all` shard + queryable parent | `CostStatisticsQueryService` | `cost-statistics` | `all` 遇 durable active dependency先快速返回 refreshing；排空后复用shared Workbench v7 proof并做Cost/Bank Detail完整fail-closed proof；只忽略Workbench执行游标`source_version`；Workbench/Cost各两个bounded consumer并行sibling month，Workbench primary唯一拥有`all` fan-out | `migrated` |
| `tax_offset` | `tax_offset`; month；`all=fan_out_command` | `TaxOffsetQueryService` | `tax-offset` | exact invoice/certified source versions；普通写零 refresh，访问 current month 收敛 | `migrated` |
| `no_oa_bank_batch` | `no_oa_bank_batch`; month；`all=fan_out_command` | `NoOaBankBatchApplicationService` | legacy API/regression only | exact canonical no-OA relation versions；不新增页面依赖 | `migrated` |
| `bank_flow_rule_batch` | `bank_flow_rule_batch`; month；`all=fan_out_command` | `BankFlowRuleBatchApplicationService` | `bank-flow-rule-batches` | exact bank/tag eligibility/relation versions；普通写零 target | `migrated` |
| `turnover_ledger` | `turnover_ledger`; month；`all=fan_out_command` | `TurnoverLedgerQueryService` | `turnover-ledger` | exact ledger + canonical relation source bundle；普通写零 target | `migrated` |

## Mutating frontend API function coverage

第一列使用“feature api.ts + exported function”的组合机械覆盖 ID。一个 HTTP method 是 POST/PUT/PATCH/DELETE 不等于业务写；`read-like-command` 行明确给出无 durable business mutation 的证据。`Current -> target` 在 slice 完成前保持 `planned`。

| Function coverage ids | API route family / UI owner | Class | Canonical owner / exact contract | Dependent read models | Current -> target / deletion | Test and production probe |
| --- | --- | --- | --- | --- | --- | --- |
| `backgroundJobs/api.ts#acknowledgeBackgroundJob`<br>`backgroundJobs/api.ts#retryBackgroundJob`<br>`backgroundJobs/api.ts#retryBackgroundJobById` | `/api/background-jobs/**`; App Health/settings | `explicit-batch` | runtime job/audit identity | job-declared targets only | retain explicit operator path；不转换为普通页面 fan-out | `test_background_jobs`; `p27-op-background-job` |
| `bankDetails/api.ts#assignBankDetailCategory`<br>`bankDetails/api.ts#clearBankDetailCategoryAssignment`<br>`bankDetails/api.ts#confirmBankDetailCategory`<br>`bankDetails/api.ts#revokeBankDetailCategoryConfirmation` | `/api/bank-details/transactions/**`; bank details row controls | `fact-write` | bank transaction classification fact + transaction month/version | `bank_detail`; semantic consumers on access | current barrier/fan-out -> exact current-page reconcile；delete downstream ordinary fan-out | `test_bank_details_*`; `p27-op-bank-category` |
| `bankDetails/api.ts#saveBankAutoTagRules` | `/api/bank-details/auto-tag-rules`; `AutoTagRulesDrawer` save | `rule-write` | auto-tag rule/settings version + changed semantic tag set | `bank_detail`, `bank_flow_rule_batch`, semantic consumers | no default all rebuild；access compares rule signature | `test_bank_details_*`; `p27-op-bank-rule-save` |
| `bankDetails/api.ts#reapplyBankAutoTagRules` | `/api/bank-details/auto-tag-rules/reapply`; Drawer explicit action | `explicit-batch` | bounded rule application job + exact affected months | `bank_detail` then semantic consumers | retain explicit bulk workflow; remove implicit full-page wait | `test_bank_details_*`; `p27-op-bank-rule-reapply` |
| `bankFlowRuleBatches/api.ts#saveBankFlowRuleBatchTagSelection` | `/api/bank-flow-rule-batches/tag-selection`; tag Drawer | `rule-write` | eligibility tag-code set/signature + affected months | `bank_flow_rule_batch` | save version, exact affected scopes only; no empty-month all fallback | `test_bank_flow_rule_batch_*`; `p27-op-bank-flow-rule` |
| `bankFlowRuleBatches/api.ts#submitBankFlowRuleBatch`<br>`bankFlowRuleBatches/api.ts#submitBankFlowRuleBatchSelection`<br>`bankFlowRuleBatches/api.ts#submitBankFlowRuleBatches`<br>`bankFlowRuleBatches/api.ts#withdrawBankFlowRuleBatch` | `/api/bank-flow-rule-batches/**`; page batch controls | `explicit-batch` | batch/relation facts + changed batch ids/months | `bank_flow_rule_batch`; relation/workbench consumers on access | commit batch delta; delete broad lifecycle and cross-page wait | `test_bank_flow_rule_batch_*`; `p27-op-bank-flow-batch` |
| `batchAccounting/api.ts#submitBatchAccounting`<br>`batchAccounting/api.ts#withdrawBatchAccounting` | `/api/batch-accounting/**`; OA selection/submitted bucket | `fact-write` | canonical Workbench relation case/row ids + months | `workbench_relation`; workbench/cost/invoice consumers on access | relation commit only + exact visible-page reconcile | `test_batch_accounting_*`; `p27-op-batch-accounting` |
| `batchAccounting/api.ts#saveBatchAccountingTagRules` | `/api/batch-accounting/tag-rules`; tag rules Drawer | `rule-write` | settings 内稳定标签代码集合与 CAS version | none；batch accounting 直接查询 current-effective 分类 | 语义保存后只重新查询当前可见页；不 fan-out、不 rebuild read model | `test_batch_accounting_*`; `p27-op-batch-accounting-tag-rule` |
| `cost-statistics/api.ts#saveCostStatisticsTagRules` | `/api/cost-statistics/tag-rules`; tag rules Drawer | `rule-write` | app settings rule version; query-time filter contract | none for rebuild; `cost_statistics` query reads rule | delete save-and-sync barrier/rebuild; refetch current view | `test_cost_statistics_*`; `p27-op-cost-rule` |
| `etc/api.ts#previewEtcZipFiles`<br>`etc/api.ts#importEtcZipFiles` | `/api/etc/import/preview`; import preview | `read-like-command` | transient preview/session only; no canonical business fact | none | no dirty/enqueue/barrier | `test_etc_*`; `p27-op-etc-preview` |
| `etc/api.ts#confirmEtcImportSession` | `/api/etc/import/confirm`; import confirm | `explicit-batch` | import session/job + exact imported identities | affected invoice/search resources | durable job acceptance; access-driven consumers | `test_etc_import_*`; `p27-op-etc-import` |
| `etc/api.ts#createEtcReconciliationTask`<br>`etc/api.ts#deleteEtcReconciliationSourceFile`<br>`etc/api.ts#deleteEtcReconciliationTask`<br>`etc/api.ts#deleteEtcReconciliationTaskImportedInvoices`<br>`etc/api.ts#patchEtcReconciliationItem`<br>`etc/api.ts#refreshEtcReconciliationMatches`<br>`etc/api.ts#reopenEtcReconciliationTask`<br>`etc/api.ts#confirmEtcReconciliationTask`<br>`etc/api.ts#uploadEtcCreditCardStatement`<br>`etc/api.ts#uploadEtcSupplementEvidenceForCard`<br>`etc/api.ts#uploadEtcSupplementEvidences`<br>`etc/api.ts#uploadEtcTicketRootFiles`<br>`etc/api.ts#uploadEtcTicketRootTexts` | `/api/etc/reconciliation-tasks/**`; ETC workflow | `explicit-batch` | reconciliation task/item/source file state + task version | task-local; imported invoice consumers only after explicit confirm | keep task job boundary; remove unrelated page fan-out | `test_etc_reconciliation_*`; `p27-op-etc-task` |
| `etc/api.ts#createEtcBusinessBatch`<br>`etc/api.ts#createEtcBusinessBatchOaDraft`<br>`etc/api.ts#deleteEtcBusinessBatch`<br>`etc/api.ts#manualEtcBusinessBatchOaStatus`<br>`etc/api.ts#revokeEtcBusinessBatchOaDraft` | `/api/etc/business-batches/**`; ETC batch/OA controls | `fact-write` | ETC business batch/OA draft identity + version; external side effect receipt where applicable | ETC page canonical query | current page refetch only; external OA remains explicit audited I/O | `test_etc_business_batch_*`; `p27-op-etc-batch` |
| `imports/api.ts#previewImportFiles`<br>`imports/api.ts#retryImportFiles` | `/imports/files/preview|retry`; import pages | `read-like-command` | transient upload/import session; retry prepares/continues session | none until confirm | no page fan-out; retry job status remains observable | `test_import_*`; `p27-op-import-preview` |
| `imports/api.ts#confirmImportFiles` | `/imports/files/confirm`; import pages | `explicit-batch` | import session/job + exact fact identities/months | import-type dependent | bounded accept/commit; exact downstream scopes, consumers on access | `test_import_processing_*`; `p27-op-import-confirm` |
| `inputInvoiceUsage/api.ts#saveInputInvoiceUsagePaymentStatusRules` | `/api/input-invoice-usage/payment-status-rules`; rules Drawer | `rule-write` | payment-status rule version/signature | `input_invoice_usage` query semantic | delete save-and-refresh-all; current access checks signature | `test_input_invoice_usage_*`; `p27-op-input-rule` |
| `inputInvoiceUsage/api.ts#previewInputInvoiceUsageOaReverse` | `/api/input-invoice-usage/oa-reverse/preview`; OA Drawer | `read-like-command` | preview DTO/canCreateDraft; no durable mutation | none | no dirty/enqueue | `test_input_invoice_usage_*`; `p27-op-input-oa-preview` |
| `inputInvoiceUsage/api.ts#createInputInvoiceUsageOaReverseBatch`<br>`inputInvoiceUsage/api.ts#createInputInvoiceUsageOaReverseDraftFromSelection` | `/api/input-invoice-usage/oa-reverse/**`; OA Drawer | `explicit-batch` | selected invoice set + OA batch/draft receipt | input usage page own scope | accept job/draft; no unrelated page fan-out | `test_input_invoice_usage_*`; `p27-op-input-oa-batch` |
| `inputInvoiceUsage/api.ts#createInputInvoiceUsageOaReverseDraft`<br>`inputInvoiceUsage/api.ts#manualInputInvoiceUsageOaReverseStatus`<br>`inputInvoiceUsage/api.ts#refreshInputInvoiceUsageOaReverseStatus`<br>`inputInvoiceUsage/api.ts#revokeInputInvoiceUsageOaReverseDraft` | `/api/input-invoice-usage/oa-reverse/**`; OA Drawer | `fact-write` | OA draft/status identity + version/external receipt | `input_invoice_usage` current scope | current Drawer/state refetch; access-time read model proof | `test_input_invoice_usage_*`; `p27-op-input-oa-state` |
| `oaPendingPayments/api.ts#linkOaPendingPaymentBankTransactions`<br>`oaPendingPayments/api.ts#writebackOaPendingPaymentPaid` | `/api/oa-pending-payments/**`; OA page | `fact-write` | OA payment/relation facts + exact OA/bank ids/months | `oa_pending_payment`; other relation consumers on access | commit only + visible page exact reconcile; delete cross-page fan-out waits | `test_oa_pending_payment_*`; `p27-op-oa-pending` |
| `operationBarrier/api.ts#fetchOperationBarrierStatus`<br>`operationBarrier/api.ts#waitForOperationFreshness` | `/api/operation-barrier/status`; shared client | `read-like-command` | current-effective readiness/dirty/outbox query only | caller-declared targets | retain for explicit ops/strict same-page transition; migrate ordinary cross-page waits | `test_operation_freshness_barrier`; `p27-op-barrier` |
| `pendingInvoices/api.ts#fetchPendingInvoiceCandidatesBatch`<br>`pendingInvoices/api.ts#previewAttachExistingInvoice`<br>`pendingInvoices/api.ts#previewAttachExistingInvoices` | `/api/pending-invoices/**/preview|candidates`; picker/relations Drawers | `read-like-command` | candidates/preview from current facts; no durable mutation | none | no dirty/enqueue | `test_pending_invoice_*`; `p27-op-pending-preview` |
| `pendingInvoices/api.ts#savePendingInvoiceRules` | `/api/pending-invoices/rules`; rules Drawer | `rule-write` | pending rule version/signature + direction | `pending_invoice` semantic scopes on access | no automatic all rebuild; exact current page scope | `test_pending_invoice_*`; `p27-op-pending-rule` |
| `pendingInvoices/api.ts#confirmAttachExistingInvoice`<br>`pendingInvoices/api.ts#confirmAttachExistingInvoices`<br>`pendingInvoices/api.ts#savePendingInvoiceIncomeStatus`<br>`pendingInvoices/api.ts#savePendingInvoiceIncomeStatuses` | `/api/pending-invoices/**`; picker/batch status | `fact-write` | invoice relation/income status facts + exact identities/months | `pending_invoice`, lifecycle/usage/collection exact consumers | commit + visible scope reconcile; no broad downstream fan-out | `test_pending_invoice_*`; `p27-op-pending-fact` |
| `tax/api.ts#calculateTaxOffset`<br>`tax/api.ts#previewTaxCertifiedImport` | `/api/tax-offset/calculate|certified-import/preview`; tax page | `read-like-command` | calculation/preview payload only | none | no dirty/enqueue | `test_tax_offset_*`; `p27-op-tax-preview` |
| `tax/api.ts#saveTaxOffsetPlan` | `/api/tax-offset/plans`; tax page | `fact-write` | tax plan fact/version + exact month | `tax_offset` current month | commit + current month reconcile | `test_tax_offset_*`; `p27-op-tax-plan` |
| `tax/api.ts#confirmTaxCertifiedImport` | `/api/tax-offset/certified-import/confirm`; tax page | `explicit-batch` | import receipt + certified invoice identities/months | `tax_offset`, invoice resources on access | bounded accept/commit; exact scopes | `test_tax_offset_*`; `p27-op-tax-import` |
| `turnoverLedger/api.ts#saveTurnoverLedgerTagSelection` | `/api/turnover-ledger/tag-selection`; tag Drawer | `rule-write` | turnover eligibility tag set/signature | `turnover_ledger` semantic scopes | no full-history rebuild on save; exact active scope | `test_turnover_ledger_*`; `p27-op-turnover-rule` |
| `turnoverLedger/api.ts#confirmTurnoverClosure`<br>`turnoverLedger/api.ts#confirmTurnoverRelation`<br>`turnoverLedger/api.ts#saveTurnoverBankRowTags`<br>`turnoverLedger/api.ts#saveTurnoverRelationExtra`<br>`turnoverLedger/api.ts#withdrawTurnoverClosure`<br>`turnoverLedger/api.ts#withdrawTurnoverRelation` | `/api/turnover-ledger/**`; detail/extra/closure | `fact-write` | ledger tag/extra + canonical relation facts and exact bank/OA ids/months | `turnover_ledger`; workbench/cost consumers on access | commit only + current ledger exact reconcile；delete broad transaction fan-out | `test_turnover_ledger_*`; `p27-op-turnover-fact` |
| `workbench/api.ts#previewWorkbenchConfirmLink`<br>`workbench/api.ts#previewWorkbenchException`<br>`workbench/api.ts#previewWorkbenchWithdrawLink` | `/api/workbench/actions/**/preview`; Workbench dialogs | `read-like-command` | preview/candidate/conflict DTO only | none | no dirty/enqueue | `test_workbench_*`; `p27-op-workbench-preview` |
| `workbench/api.ts#applyWorkbenchException`<br>`workbench/api.ts#cancelWorkbenchCashSpecial`<br>`workbench/api.ts#cancelWorkbenchLink`<br>`workbench/api.ts#confirmWorkbenchCashPassThrough`<br>`workbench/api.ts#confirmWorkbenchCashTicketPurchase`<br>`workbench/api.ts#confirmWorkbenchLink`<br>`workbench/api.ts#confirmWorkbenchPersonalAdvanceRepayment`<br>`workbench/api.ts#ignoreWorkbenchRow`<br>`workbench/api.ts#markWorkbenchException`<br>`workbench/api.ts#setWorkbenchOaInvoiceAnomalyIgnored`<br>`workbench/api.ts#updateWorkbenchBankException`<br>`workbench/api.ts#withdrawWorkbenchLink` | `/api/workbench/actions/**`, `/api/workbench/exception/**`, `/api/workbench/exceptions/amount-mismatch/**`; Workbench | `fact-write` | canonical relation/exception/ignore/cash facts + case/row ids/months/generation precondition | `workbench` visible scope; all other consumers on access | UoW commit + exact active generation reconcile；delete downstream ordinary fan-out | `test_workbench_*`; `p27-op-workbench-fact` |
| `workbench/api.ts#createWorkbenchSettingsProject`<br>`workbench/api.ts#deleteOaApplicantCredential`<br>`workbench/api.ts#deleteWorkbenchSettingsProject`<br>`workbench/api.ts#saveOaApplicantCredential`<br>`workbench/api.ts#saveWorkbenchAccessControl`<br>`workbench/api.ts#saveWorkbenchSettings`<br>`workbench/api.ts#syncWorkbenchSettingsProjects` | `/api/workbench/settings**`; settings | `rule-write` | settings/project/credential/access-control versions; secrets never enter read-model events | only semantic consumers on access | no default rebuild-all; exact version/signature comparison | `test_app_settings_*`; `p27-op-settings` |
| `workbench/api.ts#importManualOaRows`<br>`workbench/api.ts#removeManualOaImport` | `/api/workbench/settings/manual-oa-imports/**`; settings table | `fact-write` | manual OA fact ids/version | `search`, workbench/related consumers on access | commit + settings table refetch; remove broad waits | `test_manual_oa_*`; `p27-op-manual-oa` |
| `workbench/api.ts#refreshManualOaImportAttachments`<br>`workbench/api.ts#resetWorkbenchSettingsData` | `/api/workbench/settings/**/refresh|reset`; settings/admin | `explicit-batch` | job receipt + exact source identity/audit | job-declared scopes | explicit observed job; no hidden ordinary fan-out | `test_data_reset_*`; `p27-op-settings-batch` |

## Drawer component coverage

所有业务 `*Drawer.tsx` 都必须在本表双向登记；`AppDrawer.tsx` 是 layout primitive，不是业务操作入口。`read-only` 行明确无 mutation contract；`mixed` 表示 Drawer 既有只读内容又有受权限保护的写动作。

| Drawer source | Page | Classification | Mutation / save contract | Target behavior |
| --- | --- | --- | --- | --- |
| `web/src/components/batchAccounting/BatchAccountingTagRulesDrawer.tsx` | batch accounting | `writable` | `saveBatchAccountingTagRules` | read-export 只读；CAS 保存后只刷新当前页，不 fan-out |
| `web/src/components/common/OaDraftPrefillDrawer.tsx` | ETC / input usage | `writable` | `saveOaDraftPrefill` | 仅 admin 展示入口和保存；两个独立 setting family 使用 version CAS，零 read-model fan-out |
| `web/src/components/cost-statistics/CostTransactionDetailDrawer.tsx` | cost | `read-only` | none | freshness-gated transaction detail read only |
| `web/src/components/cost-statistics/CostStatisticsTagRulesDrawer.tsx` | cost | `writable` | `saveCostStatisticsTagRules` | rule version save；不 rebuild read model |
| `web/src/components/inputInvoiceUsage/InputInvoiceUsageDetailDrawer.tsx` | input usage | `read-only` | none | freshness-gated detail read only |
| `web/src/components/inputInvoiceUsage/InputInvoiceUsageExportDrawer.tsx` | input usage | `read-only` | none | export read only；不得 dirty |
| `web/src/components/inputInvoiceUsage/OaReverseWorkspaceDrawer.tsx` | input usage | `mixed` | preview read-like；draft/batch/status/revoke writes | preview zero mutation；writes only exact current scope |
| `web/src/components/inputInvoiceUsage/PaymentStatusRulesDrawer.tsx` | input usage | `writable` | `saveInputInvoiceUsagePaymentStatusRules` | rule version save；access-time semantic proof |
| `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionDetailDrawer.tsx` | output collection | `read-only` | none | canonical invoice/bank/formal-relation detail read only |
| `web/src/components/outputInvoiceCollections/OutputInvoiceCollectionExportDrawer.tsx` | output collection | `read-only` | none | export read only；不得 dirty |
| `web/src/components/pendingInvoices/PendingInvoiceDetailDrawer.tsx` | pending invoice | `read-only` | none | freshness-gated detail read only |
| `web/src/components/pendingInvoices/PendingInvoiceExportDrawer.tsx` | pending invoice | `read-only` | none | export read only；不得 dirty |
| `web/src/components/pendingInvoices/PendingInvoiceInvoicePickerDrawer.tsx` | pending invoice | `mixed` | candidate/preview read-like；confirm attach write | preview no mutation；confirm exact identity scope |
| `web/src/components/pendingInvoices/PendingInvoiceRelationDrawer.tsx` | pending invoice | `read-only` | none | relation detail read only |
| `web/src/components/pendingInvoices/PendingInvoiceRulesDrawer.tsx` | pending invoice | `writable` | `savePendingInvoiceRules` | rule signature save；current page exact scope only |
| `web/src/components/tax/CertifiedResultsDrawer.tsx` | tax offset | `read-only` | none | import result read only；confirm lives outside result Drawer |
| `web/src/components/turnoverLedger/TurnoverLedgerExtraDrawer.tsx` | turnover | `writable` | `saveTurnoverRelationExtra` | exact relation/ledger scope |
| `web/src/components/workbench/DetailDrawer.tsx` | workbench | `read-only` | none | active-generation detail read only |
| `web/src/components/workbench/WorkbenchExceptionDrawer.tsx` | workbench | `mixed` | amount-mismatch ignore/restore、legacy exception/ignore recovery | read-export 只读；写角色只提交 exact group/fingerprint/generation command |
| `web/src/features/bankDetails/AutoTagRulesDrawer.tsx` | bank details | `writable` | save rules / explicit reapply | save rule version；reapply remains explicit batch |

## Executable dynamic opener coverage

这些 ID 由 `permissions-role-matrix.spec.ts` 提供真实浏览器 opener；本表与该 registry、权限 inventory 三方双向校验。

| Opener id | Classification | Phase 27 operation owner |
| --- | --- | --- |
| `reconciliation-workbench:unpaired-actions` | `writable` | workbench relation/exception/settings |
| `reconciliation-workbench:paired-withdraw-actions` | `writable` | workbench withdraw |
| `reconciliation-workbench:cash-special-actions` | `writable` | workbench cash facts |
| `bank-details:auto-tag-rules` | `writable` | bank rule save/reapply |
| `cost-statistics:tag-rules` | `writable` | cost rule save |
| `bank-details:category-confirmation` | `writable` | bank classification fact |
| `bank-details:manual-category-assignment` | `writable` | bank classification fact |
| `bank-flow-rule-batches:tag-drawer` | `writable` | bank-flow rule/batch |
| `pending-invoices:expense-rules` | `writable` | pending rules/attach |
| `pending-invoices:income-rules` | `writable` | pending rules |
| `pending-invoices:income-batch` | `writable` | pending income status |
| `input-invoice-usage:payment-rules` | `writable` | input rules |
| `input-invoice-usage:oa-reverse` | `mixed` | preview + OA writes |
| `output-invoice-collections:canonical-read-only` | `read-only` | canonical GET/detail/export；业务 mutation 为 0 |
| `oa-pending-payments:in-progress` | `writable` | OA relation/writeback |
| `oa-pending-payments:expense-rules` | `writable` | OA expense rule |
| `etc-tickets:reconciliation-workflow` | `writable` | ETC explicit task |
| `batch-accounting:oa-selection` | `writable` | batch relation submit |
| `batch-accounting:submitted-withdraw` | `writable` | batch relation withdraw |
| `turnover-ledger:tag-drawer` | `writable` | turnover rule save |
| `turnover-ledger:detail-controls` | `writable` | turnover fact writes |
| `reconciliation-workbench:exception-drawer` | `writable` | workbench amount-mismatch and legacy recovery writes |

## Lifecycle, enqueue and barrier call sites

这里登记的是 Phase 27 必须逐一处理的直接调用点：backend `.plan_event(`、直接 `.enqueue_read_model_refresh(` / `.enqueue_read_model_refreshes_in_transaction(`，以及 frontend `waitForOperationFreshness(` 的生产 caller。Gateway 的构造/内部委托由 read-model 模块已有 manifest/boundary tests 管理，不在此复制第二套 runtime registry。

| Site id | Source file | Sentinel | Calls | Status | Owner / target and deletion condition |
| --- | --- | --- | --- | --- | --- |
| `life-server-maintenance` | `backend/src/fin_ops_platform/app/server.py` | `.plan_event(` | `1` | `retain` | 仅显式 settings reset / historical ETC repair；普通写入口已删除 |
| `enqueue-runtime-queue-batch-delegate` | `backend/src/fin_ops_platform/services/runtime_queue.py` | `.enqueue_read_model_refreshes_in_transaction(` | `1` | `retain` | 原子 inactive-scope 去重入口的事务内批量委托；属于 durable queue 内部边界，不是业务 fan-out producer |
| `barrier-cost-page` | `web/src/pages/CostStatisticsPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | route/query/manual reload/retry 复用正常 GET；refreshing 使用 150ms、最多 200 次的可取消自身重试；浏览器生命周期/跨页事件零 I/O |
| `barrier-input-page` | `web/src/pages/InputInvoiceUsagePage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | ordinary writes改为 visible scope normal GET；OA reverse 也不等待跨页 barrier |
| `barrier-batch-accounting-page` | `web/src/pages/BatchAccountingPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | relation commit 后当前可见页面正常 GET，无跨页 targets |
| `barrier-tax-page` | `web/src/pages/TaxOffsetPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | plan/certified import 提交后重跑 current month normal GET；freshness gate 精确收敛 |
| `barrier-turnover-page` | `web/src/pages/TurnoverLedgerPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | command 后只重跑 current ledger normal GET；删除 Workbench/search/cost cross-page wait |
| `barrier-workbench-page` | `web/src/pages/ReconciliationWorkbenchPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | command 后只重跑当前 active-generation normal GET；下游页面访问时收敛 |
| `barrier-etc-page` | `web/src/pages/EtcTicketManagementPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | import/ordinary batch write 后只重跑当前 ETC canonical query；其它页面访问收敛 |
| `barrier-oa-page` | `web/src/pages/OaPendingPaymentsPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | `202` 与普通写后刷新都只复用当前 rows normal GET；显式 Audit barrier 仅归 Audit icon owner |
| `barrier-pending-page` | `web/src/pages/PendingInvoicesPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | 当前 direction/filter/month normal GET；rule save 不 rebuild all |
| `barrier-output-page` | `web/src/pages/OutputInvoiceCollectionsPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | canonical direct GET/detail/export；无 receipt settings 或跨页 barrier |
| `barrier-bank-flow-page` | `web/src/pages/BankFlowRuleBatchPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | 规则/submit/withdraw/reset 成功后只重跑当前 normal GET |
| `barrier-manual-oa-table` | `web/src/components/settings/OaManualSearchImportTable.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | settings table refetch；search 在访问时收敛 |
| `barrier-oa-audit-icon` | `web/src/components/oaPendingPayments/OaPendingPaymentAuditIcon.tsx` | `waitForOperationFreshness(` | `0` | `delete` | canonical direct-read 页面 Audit 只执行单次只读检查，不再等待 OA read-model freshness |
| `barrier-import-workflow` | `web/src/components/imports/ImportWorkflowPage.tsx` | `waitForOperationFreshness(` | `0` | `deleted-local` | import job completion 只确认事实提交；受影响页面访问时 exact-scope 收敛 |

## Migration and deletion rule

1. 先在 query/read facade 建立 canonical source/rule/version mismatch proof，并测试 `fresh/stale/refreshing/error/empty`；没有 read-side proof 不得删除 write-side dirty signal。
2. 再把一个 vertical slice 的普通写收窄为 canonical commit receipt + 当前页面 exact reconcile；其它页面不发 I/O，只在 route 重进/查询变化/浏览器手动刷新/明确重试时触发同一 query contract。
3. 最后删除该 slice 的 lifecycle broad target、事务内 downstream fan-out、前端 cross-page barrier、重复 helper 与旧测试断言。禁止平行保留 fallback。
4. explicit batch 保留 durable job/outbox，但必须输出 changed identities/scopes，不用 `all` 掩盖未知影响；full-history 是显式例外，不属于普通写 3 秒“全部重建”承诺。
5. 每行只有在单元、service、API、read-model/worker、frontend、E2E、回归门禁和部署后生产 probe 都通过后才能从 `planned` 改为 `migrated`。生产 fixture 必须 test-owned、可逆、最终恢复 inactive/clean，并复跑 System Audit。
