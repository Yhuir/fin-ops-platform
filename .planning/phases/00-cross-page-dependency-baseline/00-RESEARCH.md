# Phase 0: Cross-Page Dependency Baseline - Research

**Date:** 2026-06-16
**Scope:** All 17 registered pages plus shared runtime/read-model/worker/legacy boundaries.

## Executive Summary

The app is not a set of isolated pages. It is a finance data pipeline:

```text
imports / OA / user writes
  -> canonical facts and relation write models
  -> derived lifecycle events
  -> dirty scopes and durable queue
  -> runtime workers
  -> SQL read models / Workbench active generations
  -> pages through API clients and freshness gates
```

The current architecture is directionally reasonable: long-term docs already define page ownership, read model freshness, durable queue truth, App Status registries, and worker governance. The main implementation risk is not missing documentation; it is that many active HTTP paths still pass through `server.py`, multiple route modules coexist with legacy dispatch paths, and some compatibility workers/routes remain transitional. Page phases must therefore treat old logic cleanup as an explicit gate, not an incidental refactor.

## Page Inventory

| Phase | Page | Route | Frontend entry | API client | Backend owner | Read model / worker / status |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 外部往来款管理 | `/turnover-ledger` | `web/src/pages/TurnoverLedgerPage.tsx` | `web/src/features/turnoverLedger/api.ts` | `routes_turnover_ledger.py`, `turnover_ledger_*` services, some `server.py` dispatch | `turnover_ledger`, worker `turnover-ledger`, App Status `turnover_ledger` |
| 2 | 银行明细 | `/bank-details` | `web/src/pages/BankDetailsPage.tsx` | `web/src/features/bankDetails/api.ts` | `routes_bank_details.py`, bank detail services, some `server.py` dispatch | `bank_detail`, `bank_account_balance`, workers `bank-detail`, `bank-account-balance` |
| 3 | 税金抵扣 | `/tax-offset` | `web/src/pages/TaxOffsetPage.tsx` | `web/src/features/tax/api.ts` | `routes_tax.py`, tax offset services, some `server.py` dispatch | `tax_offset`, `invoice_lifecycle`, workers `tax-offset`, `invoice-lifecycle` |
| 4 | 关联台 | `/` | `web/src/pages/ReconciliationWorkbenchPage.tsx` | `web/src/features/workbench/api.ts` | `routes_workbench.py`, workbench services, active generation, `server.py` dispatch | `workbench`, `workbench_relation`, workers `workbench`, `workbench-relation`, `workbench-matching` |
| 5 | 成本统计 | `/cost-statistics` | `web/src/pages/CostStatisticsPage.tsx` | `web/src/features/cost-statistics/api.ts` | `routes_cost_statistics.py`, cost statistics services, some `server.py` dispatch | `cost_statistics`, worker `cost-statistics`; legacy compatibility worker `cost-tax` exists |
| 6 | 待找发票 | `/pending-invoices` | `web/src/pages/PendingInvoicesPage.tsx` | `web/src/features/pendingInvoices/api.ts` | `routes_pending_invoices.py`, pending invoice services, some `server.py` dispatch | `pending_invoice`, `search`, `invoice_lifecycle`, workers `pending-invoice`, `search`, `invoice-lifecycle`; compatibility `search-pending` exists |
| 7 | 进项发票使用情况 | `/input-invoice-usage` | `web/src/pages/InputInvoiceUsagePage.tsx` | `web/src/features/inputInvoiceUsage/api.ts` | input invoice usage services, `server.py` dispatch | `input_invoice_usage`, `invoice_lifecycle`, worker `invoice-usage-collection` |
| 8 | OA待付款核对 | `/oa-pending-payments` | `web/src/pages/OaPendingPaymentsPage.tsx` | `web/src/features/oaPendingPayments/api.ts` | `routes_oa_pending_payments.py`, OA pending payment services, some `server.py` dispatch | `oa_pending_payment`, `invoice_lifecycle`, worker `invoice-usage-collection`, `oa-sync` |
| 9 | 销项发票收款情况 | `/output-invoice-collections` | `web/src/pages/OutputInvoiceCollectionsPage.tsx` | `web/src/features/outputInvoiceCollections/api.ts` | `routes_output_invoice_collections.py`, output collection services, some `server.py` dispatch | `output_invoice_collection`, `invoice_lifecycle`, worker `invoice-usage-collection` |
| 10 | 免OA流水批量处理 | `/no-oa-bank-batches` | `web/src/pages/NoOaBankBatchPage.tsx` | `web/src/features/noOaBankBatches/api.ts` | `routes_no_oa_bank_batches.py`, no-OA services, some `server.py` dispatch | `no_oa_bank_batch`, worker `no-oa-bank-batch` |
| 11 | 批量账务 | `/batch-accounting` | `web/src/pages/BatchAccountingPage.tsx` | `web/src/features/batchAccounting/api.ts` | batch accounting service, Workbench relation services, `server.py` dispatch | `workbench_relation`, worker `workbench-relation` |
| 12 | ETC票据管理 | `/etc-tickets` | `web/src/pages/EtcTicketManagementPage.tsx` | `web/src/features/etc/api.ts` | `routes_etc.py`, ETC services, `server.py` dispatch | import worker, ETC import/business batch state, Workbench impact |
| 13 | 设置 | `/settings` | `web/src/pages/SettingsPage.tsx` | `web/src/features/workbench/api.ts` settings endpoints | settings services, `server.py` dispatch | `oa-sync`, settings refresh jobs, dependencies `oa_identity`, `state_store` |
| 14 | 系统状态 | `/operations/app-health` | `web/src/pages/AppHealthOperationsPage.tsx` | `web/src/features/appHealth/api.ts`, `web/src/features/appStatus/api.ts` | app health/status services, runtime monitoring, `server.py` dispatch | App Status domains, workers, queue, dependencies |
| 15 | 银行流水导入 | `/imports/bank-transactions` | `web/src/pages/imports/ImportBankTransactionsPage.tsx` | `web/src/features/imports/api.ts` | import file/processing/job services, `server.py` import endpoints | import worker, `bank_transaction_import`, downstream bank/workbench/cost/search |
| 16 | 发票导入 | `/imports/invoices` | `web/src/pages/imports/ImportInvoicesPage.tsx` | `web/src/features/imports/api.ts` | import file/processing/job services, `server.py` import endpoints | import worker, `invoice_import`, downstream invoice lifecycle/workbench/tax/cost/search |
| 17 | ETC发票导入 | `/imports/etc-invoices` | `web/src/pages/imports/ImportEtcInvoicesPage.tsx` | `web/src/features/etc/api.ts`, import route helpers | ETC/import services, `server.py` `/api/etc/import*` | import worker, `etc_invoice_import`, downstream ETC/workbench/tax/cost/search |

## Current Architecture Assessment

### Reasonable Baselines

- Page registry is centralized in `web/src/app/pageRegistry.tsx`.
- App architecture docs already distinguish page-local UI state from durable business facts.
- `ReadModelQueryGateway`, `ReadModelRefreshGateway`, scope policy registry, durable queue, App Status registries, and runtime worker registry define the correct governance shape.
- `DerivedDataLifecycleService` is the durable cross-page invalidation planning layer.
- App Status domain registry binds most user-visible domains to read models, worker instances, job types, and dependencies.
- Module docs already exist for every registered page and for key shared resources.

### Architecture Friction To Track In Page Phases

- `server.py` still contains broad dispatch for many `/api/*` paths. Existing route modules and direct `server.py` handlers coexist, so page phases must identify the canonical active boundary before changing behavior.
- Compatibility workers exist (`search-pending`, `cost-tax`) alongside more focused worker instances. Page phases must not add new dependencies on compatibility workers.
- Import pages share `ImportWorkflowPage` and import services. A change for one import page can affect bank, invoice, and ETC import behavior.
- Workbench relations are a shared write/read model boundary used by Workbench, batch accounting, no-OA batches, turnover ledger, bank details, invoice pages, tax, cost, and search.
- Frontend finance domain events are useful for same-browser refresh, but they do not prove data freshness.

## Functional Gap Baseline

Phase 0 does not decide page feature gaps. It defines how gaps must be classified in each page phase:

| Gap type | Examples | Required analysis before implementation |
| --- | --- | --- |
| Experience-only | table density, drawer flow, filters, empty/error copy, column affordances | Verify it does not alter API contract, read model shape, or cross-page state. Frontend component tests may be enough. |
| API/UI contract | new row fields, export columns, pagination/sorting/filtering shape, error payload | Update frontend mapper, backend route/service contract, API tests, docs/dev or module docs as needed. |
| Business rule | classification, relation state, invoice usage, tax/cost attribution, batch status | Business core/service tests, audit, permissions, idempotency, conflict handling, stale state. |
| Data-flow/read model | list page contents, summaries, stale/fresh states, source versions, worker rebuild | Read model/worker tests, dirty/outbox verification, App Status behavior, operation barrier. |
| Legacy cleanup | removing old route/service/repository/worker path | Caller inventory, canonical-path tests, regression tests, docs cleanup, no unknown callers. |

## Risk Baseline

| Risk | Why it matters | Mandatory gate |
| --- | --- | --- |
| Permission drift | Frontend hiding controls cannot replace backend `can_mutate_data` / `can_admin_access` checks. | API contract tests for forbidden/read-only/full/admin paths when behavior changes. |
| Audit gaps | High-risk finance writes must record actor/action/object/amount or parameter summary. | Service/API tests or audit assertions for writes, imports, settings, exports, resets. |
| Fake freshness | Missing/stale read models must not be shown as fresh or empty truth. | Read model gateway tests and UI stale/refreshing/blocked states. |
| Cross-page stale data | Page A writes can affect Page B read model. | Lifecycle fan-out and operation barrier scopes must be planned. |
| Worker invisibility | App Status can only diagnose registered workers/read models/jobs. | Registry update + registry consistency tests when adding/changing workers/read models. |
| Export drift | Export columns often encode business meaning and permissions. | Export preview/blob tests and docs impact for field/permission changes. |
| Historical data pollution | Legacy Mongo/GridFS, legacy relation paths, old workers, and migrated data can re-enter current flows. | Legacy cleanup gate and migration/backfill/repair dry-run where applicable. |
| Shared workflow regression | Import workflow and Workbench relation flows serve multiple pages. | Cross-page frontend/backend regression tests, not page-only checks. |

## Seven-Category Test Matrix For Page Phases

| Test category | Phase 0 applicability | Page-phase rule |
| --- | --- | --- |
| Business core unit tests | Not applicable to Phase 0 docs-only work. | Required for business rules, state transitions, relation modes, classification, idempotency, or calculations. |
| Service-layer tests | Not applicable to Phase 0 docs-only work. | Required for services, repositories, audit, read models, background jobs, and orchestration. |
| API contract tests | Not applicable to Phase 0 docs-only work. | Required for HTTP contract, response shape, errors, permissions, stale/fresh and version conflicts. |
| Read model/cache/worker tests | Not applicable to Phase 0 docs-only work. | Required for list pages, summaries, ledgers, tax/cost, workbench, imports, and any dirty/outbox behavior. |
| Frontend component/interaction tests | Not applicable to Phase 0 docs-only work. | Required for page UI, tables, drawers, dialogs, filters, permissions, loading/empty/error/stale states. |
| E2E business-flow integration tests | Not applicable to Phase 0 docs-only work. | Required when a change crosses import -> write -> worker -> read model -> page display. |
| Existing feature regression tests | Docs-only baseline has no runtime behavior. | Always evaluate affected pages, exports, read models, permissions, and old workflows. |

Primary verification entry points are `docs/modules/<module>/tests.md`, `docs/dev/testing.md`, `docs/dev/testing-closure-dependency-map.md`, `bash scripts/verify.sh backend`, `bash scripts/verify.sh frontend`, `bash scripts/verify.sh docs`, and `bash scripts/verify.sh all`.

## Docs Impact Baseline

Every page phase must decide whether it changes:

- Long-term page/runtime facts: update `docs/app-architecture/pages.md` or `runtime-and-ownership.md`.
- Module facts: update `docs/modules/<module>/README.md`, `state-machine.md`, `tests.md`, or `implementation-notes.md`.
- API/testing facts: update `docs/dev/api-contracts.md`, `docs/dev/testing.md`, or `docs/dev/testing-closure-dependency-map.md`.
- Operations facts: update `docs/operations/runtime-worker-governance.md`, deployment docs, or runtime monitoring docs.
- Product facts: update `docs/product-specs/`.

If the change is docs-only planning or internal implementation with no contract/state/data-flow change, final responses may state docs impact is not applicable.
