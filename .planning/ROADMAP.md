# Roadmap: fin-ops-platform Page Analysis

## Overview

This roadmap preserves a single global codebase map while creating isolated GSD phases for each target page. Phase 0 establishes the cross-page dependency baseline that every page phase must read before implementation planning. Each page phase should capture discussion context, research findings, implementation risks, test strategy, and executable plans inside its own phase directory.

This roadmap is the root page-analysis roadmap. Cross-module modular IO refactor execution lives under `.planning/refactors/modular-io-boundaries/`; that refactor must still read this file as an input, but its autonomous boundary queue and phase roadmap are tracked separately in `autonomous/MODULE-QUEUE.md` and `04-IMPLEMENTATION-ROADMAP.md`.

## Phases

**Phase Numbering:**

- Integer phases (0-17): Cross-page baseline first, then page-specific analysis and planning work for every registered app page.
- Phase 18: Cross-module repair/evolution work that closes the canonical invoice + ETC batch-link boundary after the page-analysis phases exposed the issue.
- Phase 19-21: Cross-page Audit, reversible relation runtime proof, and deterministic Workbench relation visibility production closure.
- Phase 27-29: Access-time read-model convergence, Cost recovery performance, and Workbench recovery performance closure.
- Phase 26: Turnover closure ownership/completion separation, frozen policy correction, historical repair and Workbench v6 production closure. Its dependencies are logical Phase 1 and Phase 21 contracts, not the immediately preceding numeric phase.
- Decimal phases (2.1, 2.2): Urgent insertions between existing phases.

## Phase Details

### Phase 0: 建立跨页依赖基线：页面数据流、read model/worker、legacy 清理和实施顺序

**Goal:** Capture the cross-page dependency baseline required before any page implementation starts, including page inventory, upstream/downstream data flow, read model/worker ownership, legacy entry points, risk gates, test matrix, docs impact, and recommended implementation order.
**Requirements**: BASE-00, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Global `.planning/codebase/` map and long-term docs under `docs/app-architecture/` and `docs/modules/`.
**Canonical refs:** `docs/app-architecture/pages.md`, `docs/app-architecture/runtime-and-ownership.md`, `docs/modules/README.md`, `docs/modules/read-models/README.md`, `docs/modules/runtime-workers/README.md`, `docs/modules/domain-events-lifecycle/README.md`, `docs/modules/permissions-and-audit/README.md`, `docs/dev/testing-closure-dependency-map.md`, `web/src/app/pageRegistry.tsx`, `web/src/features/domainEvents.ts`, `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py`, `backend/src/fin_ops_platform/services/app_status_domain_registry.py`, `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`, `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify all registered pages, their routes, frontend entries, API clients, backend route/service boundaries, read model/worker dependencies, upstream data sources, downstream consumers, and App Status domain bindings.
  2. Cross-page data flow and lifecycle event fan-out are documented enough that a page phase can decide which other pages, read models, workers, caches, exports, and tests are affected.
  3. Legacy entry points and cleanup gates are documented so page phases can migrate callers to canonical boundaries before deleting old paths.
  4. Test matrix and docs impact rules are mapped to the repository's seven test categories and long-term module docs.
  5. Implementation order guidance distinguishes baseline analysis, page-level deep planning, strong dependency groups, and safe parallel work boundaries.

**Plans:** 9 plans

Plans:

- [x] 00-PLAN — Establish baseline artifacts and gates for downstream page phases.

### Phase 1: 完善外部往来款管理页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the external turnover ledger page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-01, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/turnover-ledger/README.md`, `docs/modules/turnover-ledger/state-machine.md`, `docs/modules/turnover-ledger/tests.md`, `web/src/pages/TurnoverLedgerPage.tsx`, `web/src/features/turnoverLedger/api.ts`, `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify turnover-ledger module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 1 to break down)

### Phase 2: 完善银行明细页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the bank details page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-02, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/bank-details/README.md`, `docs/modules/bank-details/state-machine.md`, `docs/modules/bank-details/tests.md`, `web/src/pages/BankDetailsPage.tsx`, `web/src/features/bankDetails/api.ts`, `backend/src/fin_ops_platform/services/bank_details_export_service.py`, `backend/src/fin_ops_platform/services/bank_details_relation_tag_projection_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify bank-details module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 2 to break down)

### Phase 3: 完善税金抵扣页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the tax offset page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-03, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/tax-offset/README.md`, `docs/modules/tax-offset/state-machine.md`, `docs/modules/tax-offset/tests.md`, `web/src/pages/TaxOffsetPage.tsx`, `web/src/components/tax/*`, `web/src/features/tax/api.ts`, `backend/src/fin_ops_platform/app/routes_tax.py`, `backend/src/fin_ops_platform/services/tax_offset_service.py`, `backend/src/fin_ops_platform/services/tax_offset_runtime_service.py`, `backend/src/fin_ops_platform/services/tax_offset_read_model_service.py`, `backend/src/fin_ops_platform/services/tax_offset_read_model_refresh.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify tax-offset module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 3 to break down)

### Phase 4: 完善关联台页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the reconciliation workbench page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-06, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/reconciliation-workbench/README.md`, `docs/modules/reconciliation-workbench/state-machine.md`, `docs/modules/reconciliation-workbench/tests.md`, `web/src/pages/ReconciliationWorkbenchPage.tsx`, `web/src/components/workbench/*`, `web/src/features/workbench/api.ts`, `backend/src/fin_ops_platform/app/routes_workbench.py`, `backend/src/fin_ops_platform/services/live_workbench_service.py`, `backend/src/fin_ops_platform/services/workbench_action_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify reconciliation-workbench module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 4 to break down)

### Phase 5: 完善成本统计页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the cost statistics page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-07, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/cost-statistics/README.md`, `docs/modules/cost-statistics/state-machine.md`, `docs/modules/cost-statistics/tests.md`, `web/src/pages/CostStatisticsPage.tsx`, `web/src/components/cost-statistics/*`, `web/src/features/cost-statistics/api.ts`, `backend/src/fin_ops_platform/app/routes_cost_statistics.py`, `backend/src/fin_ops_platform/services/cost_statistics_query_service.py`, `backend/src/fin_ops_platform/services/cost_statistics_read_model_refresh.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify cost-statistics module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 5 to break down)

### Phase 6: 完善待找发票页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the pending invoices page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-08, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/pending-invoices/README.md`, `docs/modules/pending-invoices/state-machine.md`, `docs/modules/pending-invoices/tests.md`, `web/src/pages/PendingInvoicesPage.tsx`, `web/src/components/pendingInvoices/*`, `web/src/features/pendingInvoices/api.ts`, `backend/src/fin_ops_platform/app/routes_pending_invoices.py`, `backend/src/fin_ops_platform/services/pending_invoice_service.py`, `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify pending-invoices module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 6 to break down)

### Phase 7: 完善进项发票使用情况页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the input invoice usage page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-09, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/input-invoice-usage/README.md`, `docs/modules/input-invoice-usage/state-machine.md`, `docs/modules/input-invoice-usage/tests.md`, `web/src/pages/InputInvoiceUsagePage.tsx`, `web/src/components/inputInvoiceUsage/*`, `web/src/features/inputInvoiceUsage/api.ts`, `backend/src/fin_ops_platform/services/input_invoice_usage_service.py`, `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify input-invoice-usage module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 7 to break down)

### Phase 8: 完善OA待付款核对页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the OA pending payments page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-10, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/oa-pending-payments/README.md`, `docs/modules/oa-pending-payments/state-machine.md`, `docs/modules/oa-pending-payments/tests.md`, `web/src/pages/OaPendingPaymentsPage.tsx`, `web/src/components/oaPendingPayments/*`, `web/src/features/oaPendingPayments/api.ts`, `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py`, `backend/src/fin_ops_platform/services/oa_pending_payment_service.py`, `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify oa-pending-payments module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 8 to break down)

### Phase 9: 完善销项发票收款情况页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the output invoice collections page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-11, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/output-invoice-collections/README.md`, `docs/modules/output-invoice-collections/state-machine.md`, `docs/modules/output-invoice-collections/tests.md`, `web/src/pages/OutputInvoiceCollectionsPage.tsx`, `web/src/components/outputInvoiceCollections/*`, `web/src/features/outputInvoiceCollections/api.ts`, `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`, `backend/src/fin_ops_platform/services/output_invoice_collection_service.py`, `backend/src/fin_ops_platform/services/output_invoice_collection_lifecycle_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify output-invoice-collections module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 9 to break down)

### Phase 10: 完善免OA流水批量处理页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the no-OA bank batches page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-12, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/no-oa-bank-batches/README.md`, `docs/modules/no-oa-bank-batches/state-machine.md`, `docs/modules/no-oa-bank-batches/tests.md`, `web/src/pages/NoOaBankBatchPage.tsx`, `web/src/features/noOaBankBatches/api.ts`, `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`, `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`, `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify no-oa-bank-batches module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 10 to break down)

### Phase 11: 完善批量账务页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the batch accounting page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-13, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/batch-accounting/README.md`, `docs/modules/batch-accounting/state-machine.md`, `docs/modules/batch-accounting/tests.md`, `web/src/pages/BatchAccountingPage.tsx`, `web/src/features/batchAccounting/api.ts`, `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify batch-accounting module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 11 to break down)

### Phase 12: 完善ETC票据管理页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the ETC ticket management page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-14, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/etc-tickets/README.md`, `docs/modules/etc-tickets/state-machine.md`, `docs/modules/etc-tickets/tests.md`, `web/src/pages/EtcTicketManagementPage.tsx`, `web/src/features/etc/api.ts`, `backend/src/fin_ops_platform/app/routes_etc.py`, `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`, `backend/src/fin_ops_platform/services/etc_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify etc-tickets module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 1 plan

Plans:

- [x] 12-01-PLAN — Deliver the direct-canonical ETC page performance path, three-bucket OA lifecycle, recoverable scoped-CAS command flow, fail-closed Audit, legacy cleanup, and release verification.

### Phase 13: 完善设置页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the settings page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/settings/README.md`, `docs/modules/settings/state-machine.md`, `docs/modules/settings/tests.md`, `web/src/pages/SettingsPage.tsx`, `web/src/components/settings/*`, `backend/src/fin_ops_platform/app/server.py`, `backend/src/fin_ops_platform/services/app_settings_service.py`, `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify settings module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 13 to break down)

### Phase 14: 完善系统状态页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the app health operations page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-16, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/app-health-operations/README.md`, `docs/modules/app-health-operations/state-machine.md`, `docs/modules/app-health-operations/tests.md`, `web/src/pages/AppHealthOperationsPage.tsx`, `web/src/features/appHealth/*`, `web/src/features/appStatus/*`, `backend/src/fin_ops_platform/services/app_health_service.py`, `backend/src/fin_ops_platform/services/app_status_overview_service.py`, `backend/src/fin_ops_platform/services/runtime_monitoring.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify app-health-operations module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 14 to break down)

### Phase 15: 完善银行流水导入页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the bank transaction import page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-17, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/imports-bank-transactions/README.md`, `docs/modules/imports-bank-transactions/state-machine.md`, `docs/modules/imports-bank-transactions/tests.md`, `web/src/pages/imports/ImportBankTransactionsPage.tsx`, `web/src/components/imports/ImportWorkflowPage.tsx`, `web/src/features/imports/api.ts`, `backend/src/fin_ops_platform/services/import_file_service.py`, `backend/src/fin_ops_platform/services/import_processing_service.py`, `backend/src/fin_ops_platform/services/import_job_queue.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify imports-bank-transactions module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 15 to break down)

### Phase 16: 完善发票导入页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the invoice import page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-18, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/imports-invoices/README.md`, `docs/modules/imports-invoices/state-machine.md`, `docs/modules/imports-invoices/tests.md`, `web/src/pages/imports/ImportInvoicesPage.tsx`, `web/src/components/imports/ImportWorkflowPage.tsx`, `web/src/features/imports/api.ts`, `backend/src/fin_ops_platform/services/import_file_service.py`, `backend/src/fin_ops_platform/services/import_processing_service.py`, `backend/src/fin_ops_platform/services/import_job_queue.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify imports-invoices module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 16 to break down)

### Phase 17: 完善ETC发票导入页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the ETC invoice import page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-19, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Phase 0 cross-page dependency baseline and global `.planning/codebase/` map.
**Canonical refs:** `docs/modules/imports-etc-invoices/README.md`, `docs/modules/imports-etc-invoices/state-machine.md`, `docs/modules/imports-etc-invoices/tests.md`, `web/src/pages/imports/ImportEtcInvoicesPage.tsx`, `web/src/components/imports/ImportWorkflowPage.tsx`, `web/src/features/etc/api.ts`, `backend/src/fin_ops_platform/services/etc_service.py`, `backend/src/fin_ops_platform/services/import_processing_service.py`, `backend/src/fin_ops_platform/services/import_job_queue.py`
**Success Criteria** (what must be TRUE):

  1. Phase artifacts identify imports-etc-invoices module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 17 to break down)

### Phase 18: 发票池与 ETC 批次关系闭环：生产修复、事实源边界和历史迁移

**Goal:** Close the duplicate-invoice defect caused by formal invoice imports overlapping submitted ETC batch history, then evolve the architecture so `app.invoices` is the single canonical invoice pool and ETC batch membership is represented by an explicit link fact instead of by duplicate workbench rows.
**Requirements**: INV-ETC-01, INV-ETC-02, INV-ETC-03, INV-ETC-04, INV-ETC-05, INV-ETC-06
**Depends on:** Phase 0 cross-page dependency baseline, Phase 4 reconciliation workbench, Phase 12 ETC ticket management, Phase 16 invoice import, Phase 17 ETC invoice import, and current module docs.
**Canonical refs:** `docs/modules/reconciliation-workbench/README.md`, `docs/modules/reconciliation-workbench/tests.md`, `docs/modules/imports-invoices/README.md`, `docs/modules/imports-invoices/tests.md`, `docs/modules/imports-etc-invoices/README.md`, `docs/modules/imports-etc-invoices/tests.md`, `docs/modules/etc-tickets/README.md`, `docs/modules/etc-tickets/tests.md`, `docs/modules/data-safety-reset/README.md`, `docs/modules/read-models/README.md`, `docs/modules/runtime-workers/README.md`, `backend/src/fin_ops_platform/postgres/migrations/0002_core_imports_invoices_bank.sql`, `backend/src/fin_ops_platform/postgres/migrations/0005_tax_etc_turnover_settings_jobs.sql`, `backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py`, `backend/src/fin_ops_platform/services/workbench_sql_projection.py`
**Success Criteria** (what must be TRUE):

  1. Phase A production stabilization prevents submitted ETC batch invoices from appearing as separate open invoice rows in the reconciliation workbench when the same real invoice exists in `app.invoices`.
  2. Phase A includes a dry-run-first database repair plan that classifies current overlap rows, preserves auditability, refreshes affected read models, and does not delete production data without an explicit apply gate.
  3. Phase B introduces `app.etc_batch_invoice_links` as the canonical ETC batch membership fact while preserving `app.invoices` as one real invoice per active row.
  4. Phase B keeps `app.etc_invoices` only as ETC source/import metadata during migration, not as a competing workbench invoice fact source.
  5. Phase C backfills historical links, removes or deprecates duplicate old paths, updates reset semantics, and documents the final long-term boundary.
  6. Excel full-mirror reconciliation is rerun before data apply: `发票基础信息` invoice identities, `信息汇总表` line rows, DB pool count, missing/extra identities, and field mismatches are all explicitly reported.
  7. Tests cover business core, service/repository, API/read-model/workbench display, import/regression, and at least one cross-module integration flow before completion.

**Plans:** 3 plans

Plans:

- [x] 18-PLAN — Execute Phase A-C as a gated master workflow driven by `18-GOAL-PROMPT.md`; implementation is closed, production apply remains gated by explicit user approval.

---

## Progress

**Execution Order:**
Phase 0 is the shared baseline and must be completed before page implementation planning. After Phase 0, page-analysis phases can run independently in separate worktree threads when they only write their assigned phase directory. Merge planning artifacts carefully if multiple threads update shared root planning files.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 0. 跨页依赖基线 | 1/1 | Complete | 2026-06-16 |
| 1. 外部往来款管理 | 0/0 | Not started | - |
| 2. 银行明细 | 0/0 | Not started | - |
| 3. 税金抵扣 | 0/0 | Not started | - |
| 4. 关联台 | 0/0 | Not started | - |
| 5. 成本统计 | 0/0 | Not started | - |
| 6. 待找发票 | 0/0 | Not started | - |
| 7. 进项发票使用情况 | 0/0 | Not started | - |
| 8. OA待付款核对 | 0/0 | Not started | - |
| 9. 销项发票收款情况 | 0/0 | Not started | - |
| 10. 免OA流水批量处理 | 0/0 | Not started | - |
| 11. 批量账务 | 0/0 | Not started | - |
| 12. ETC票据管理 | 1/1 | Complete — READY_FOR_UNIFIED_DEPLOYMENT; production gates pending | 2026-07-18 |
| 13. 设置 | 0/0 | Not started | - |
| 14. 系统状态 | 0/0 | Not started | - |
| 15. 银行流水导入 | 0/0 | Not started | - |
| 16. 发票导入 | 0/0 | Not started | - |
| 17. ETC发票导入 | 0/0 | Not started | - |
| 18. 发票池与 ETC 批次关系闭环 | 1/1 | Implementation complete, apply gated | 2026-06-23 |
| 26. 外部往来闭环冻结要求分区 | 0/2 | Planned | - |

### Phase 19: 全页面 Audit 证明、跨页关系一致性、readiness 语义与旧链路移除的生产闭环

**Goal:** Establish a production-grade, version-bound and system-snapshot Audit proof for every registered page; prove canonical/shared/consumer relation equality; unify manifest-driven current-effective readiness; remove parallel legacy Audit runtime paths; and close production verification without overstating unavailable external evidence.
**Requirements**: AUDIT-01, AUDIT-02, AUDIT-03, AUDIT-04, AUDIT-05, AUDIT-06, AUDIT-07, AUDIT-08, AUDIT-09, AUDIT-10, AUDIT-11, AUDIT-12
**Depends on:** Phase 0 cross-page baseline and the current long-term module/read-model/worker contracts. Phase 18 is relevant only where ETC invoice facts overlap page proof.
**Canonical refs:** `.planning/phases/19-audit-readiness/19-CONTEXT.md`, `.planning/phases/19-audit-readiness/19-INVENTORY.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/permissions-and-audit/boundary-io.md`, `docs/modules/app-health-operations/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Every registered page is covered by a fail-closed contract and the registry/page coverage guard passes.
  2. One read-only system snapshot proves independent expected-set equality, critical field recalculation, and canonical/shared/every-consumer relation equality with version-bound results.
  3. Audit, App Status, barriers and SLO share one manifest-driven current-effective policy; `fan_out_command/all` history cannot falsely block while real current failures still block.
  4. Specialized legacy Audit routes/modules/clients are removed after caller evidence, with no runtime fallback or duplicate fact source.
  5. Applicable seven-category tests, exact omission regression, architecture guards, docs verification and authorized production read-only closure all pass.

**Plans:** 19 plans

Plans:

- [x] 19-01-PLAN — Make manifest scope roles authoritative for command-only parent readiness and App Status current-effective aggregation.
- [x] 19-02-PLAN — Establish the 17-page Audit registry and unified page-key runtime; migrate the current 9 controls and make invoice queue proof real.
- [x] 19-03-PLAN — Prove invoice consumer relation edges bidirectionally and remove specialized HTTP Audit runtime paths.
- [x] 19-04-PLAN — Prove OA pending-payment and pending-invoice consumer relation edges bidirectionally.
- [x] 19-05-PLAN — Prove bank-detail linked relation tags, case identity, status, and active-row uniqueness.
- [x] 19-06-PLAN — Prove bank-flow rule batch canonical/page/relation status and member-set equality.
- [x] 19-07-PLAN — Prove batch-accounting direct shared-relation consumer case/mode/source equality.
- [x] 19-08-PLAN — Preserve turnover structured relation summaries and prove per-ledger-row consumer edges.
- [x] 19-09-PLAN — Unify Workbench active-generation display proof, enable the page Audit, and reduce the legacy tool to a thin CLI.
- [x] 19-10-PLAN — Prove the complete Workbench canonical object inventory, critical fields, summaries, and all-scope union.
- [x] 19-11-PLAN — Close cost-statistics upstream lineage, canonical bank set, critical fields, and source-version binding.
- [x] 19-12-PLAN — Prove tax-offset canonical invoice/certified sets, matching, fields, summaries, versions, and queue closure.
- [x] 19-13-PLAN — Prove ETC ticket direct canonical sets, internal relations, files, and import queue closure.
- [x] 19-14-PLAN — Prove Settings direct canonical configuration, credential summaries, projects, and reset queue without secret exposure.
- [x] 19-15-PLAN — Prove bank-transaction import sessions, files, batches, rows, canonical transactions, jobs, and remove the parallel legacy HTTP path.
- [x] 19-16-PLAN — Prove invoice-import files, batches, rows, canonical invoice/source-link edges, isolate page jobs, and remove inline/revert/file-batch legacy paths.
- [x] 19-17-PLAN — Make ETC invoice import sessions durable across processes, prove task/archive/preview/batch/invoice/job equality, and remove in-memory/inline/direct-import legacy paths.
- [x] 19-18-PLAN — Make App Health the fail-closed system Audit owner, run every page proof in one database snapshot, bind version/evidence sets, separate runtime/external observations, and remove the page-private invoice Audit panel.
- [x] 19-19-PLAN — Converge the 13 backend baseline failures to zero by updating stale proof fixtures/contracts and fixing stable legacy exception idempotency without weakening production gates.
- [x] 19-20-PLAN — Register immutable external complete-snapshot manifests and prove bank/OA/invoice/ETC exact sets against canonical App facts without polluting the read-only System Audit.
- [ ] 19-21-PLAN — Deploy the reviewed exact release and capture a read-only 17-page internal System Audit closure report; keep optional external source reconciliation separate and unknown when no independent evidence exists.

### Phase 20: 三组可逆关系写操作的 Fan-out、Worker、Freshness 与 System Audit 生产级闭环

**Goal:** Extend the existing controlled write-operation runner into one production-grade per-mutation closure path, then prove reversible bank+invoice, bank+turnover, and bank+OA+invoice relation shapes across canonical writes, durable fan-out, workers, freshness, affected consumers, and a new read-only System Audit after both confirm and withdraw.
**Requirements**: RELCL-01, RELCL-02, RELCL-03, RELCL-04, RELCL-05, RELCL-06, RELCL-07
**Depends on:** Phase 19
**Canonical refs:** `.planning/phases/20-fan-out-worker-freshness-system-audit/20-CONTEXT.md`, `.planning/phases/20-fan-out-worker-freshness-system-audit/20-RESEARCH.md`, `docs/architecture/module-boundaries/canonical-facts.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/modules/app-health-operations/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. One checkpoint runner proves each mutation independently; no scenario-level shortcut combines confirm and withdraw evidence.
  2. Three reversible relation shapes pass required fan-out, worker drain, freshness, affected consumer and new System Audit gates after both directions.
  3. Canonical relation, queue, freshness and Audit ownership remain modular and no test/runtime path writes derived facts directly.
  4. Retired parallel/legacy execution paths are removed after caller scan; retained adapters have explicit owner and deletion conditions.
  5. Deterministic/full regression and opt-in disposable PostgreSQL gates are complete without 17×operation duplication or external-source overclaim.

**Plans:** 1 plan

Plans:

- [x] 20-01-PLAN — Build the single checkpoint closure runner, register three reversible relation shapes, remove retired paths, and verify deterministic plus disposable-PostgreSQL evidence.

### Phase 21: 关联台确定性自动正式关系与全量可见性生产闭环

**Goal:** Replace persisted automatic candidates/decisions with one deterministic fail-closed formal-relation path, make the Workbench projection an exact partition of canonical facts into active paired groups or standalone unpaired rows, repair all-scope union omissions, remove the complete legacy runtime chain, and prove data-safe recovery through production-grade tests and controlled evidence.
**Requirements**: RELVIS-01, RELVIS-02, RELVIS-03, RELVIS-04, RELVIS-05, RELVIS-06, RELVIS-07, RELVIS-08, RELVIS-09, RELVIS-10
**Depends on:** Phase 20
**Canonical refs:** `.planning/phases/21-workbench-deterministic-relations/21-CONTEXT.md`, `docs/product-specs/workbench.md`, `docs/product-specs/reconciliation.md`, `docs/architecture/module-boundaries/canonical-facts.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. For eligible canonical facts `C`, active relation members `R`, visible paired facts `P`, and visible unpaired facts `U`: `P = R`, `U = C - R`, `P ∩ U = ∅`, and `P ∪ U = C`, with every fact represented once.
  2. Deterministic safe automatic results directly create formal active relations through the existing command/UoW boundary; no candidate/decision persistence, display state, compatibility filter or dual orchestrator path remains.
  3. Cross-month arbitrary N:M:K matching is exact, evidence-connected, bounded and ambiguity-safe; existing relations remain stable and explicit withdrawal/cancel remains the only lifecycle exit.
  4. `month=all` unions active month-shard members by canonical identity without omission or duplication, including the known 13-invoice counterexample; the Yunnan Lifu 520 OA+invoice relation is displayed as paired.
  5. Forward schema migration, read-model rebuild, worker drain, seven-category tests, data hashes and System Audit prove no canonical fact damage and no runtime access to retired candidate/decision objects.

**Plans:** 4 plans
Plans:

- [x] 21-01 — Freeze deterministic matching contracts, 520/13 fixtures and fail-closed safety rules.
- [x] 21-02 — Replace candidate/decision persistence with direct formal relation command/UoW orchestration.
- [x] 21-03 — Enforce the paired/unpaired exact visibility partition across read models, API, UI and downstream consumers.
- [ ] 21-04 — Deploy the clean cutover, run migration 0104, rehydrate registered scopes and capture production data-safety/Audit evidence.

### Phase 21.1: ETC 批次正式关系归属与折叠数量闭环

**Goal:** Make an ETC OA's exact batch marker enrich the one active formal Workbench relation, display the canonical invoice count consistently, remove obsolete operator-only link/migration paths, and prove fast isolated production convergence.
**Requirements:** RELVIS-ETC-01, RELVIS-ETC-02, RELVIS-ETC-03, RELVIS-ETC-04, RELVIS-ETC-05, RELVIS-ETC-06
**Depends on:** Phase 21 deterministic relation runtime and Phase 12 ETC business-batch state machine.
**Canonical refs:** `.planning/phases/21.1-workbench-etc-relation-enrichment/21.1-CONTEXT.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/etc-tickets/boundary-io.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Collapsed ETC summary and expansion copy both use the canonical detail count; a 34-invoice batch never renders as 35.
  2. An exact OA `etc_batch_id` and exactly one submitted ETC business batch enrich exactly one formal relation through the existing UoW/command boundary; ambiguous or conflicting ownership fails closed.
  3. Paired and unpaired projection use one canonical relation-batch resolver, so one batch has one display owner.
  4. Page Audit proves expected ETC relation enrichment and unique ownership, including post-write freshness/queue closure.
  5. Retired operator-only existing-link and historical-migration services/tools/tests/docs are removed after whole-repository caller evidence.
  6. API p95 is at most 1 second and operation-to-fresh p99 is at most 3 seconds without a new worker, table, cache, fallback, or cross-page write path.

**Plans:** 1 plan

Plans:

- [ ] 21.1-01 — Implement exact enrichment, canonical count/ownership, scoped fast convergence, Audit proof, old-path removal, and production verification.

### Phase 26: 修复外部往来闭环按冻结 OA/发票要求进入关联台分区

**Goal:** Separate canonical active relation ownership from Workbench completion for turnover manual closures; freeze the actual Bank Transaction Paired Policy at confirmation, fail closed when merged bank membership is not fully selected, remove hard-coded and legacy resync paths, repair historical invalid snapshots with fingerprint-bound exact metadata rollback that preserves relation ownership/lifecycle, upgrade Workbench to v6 and close exact-release production rehydration without adding runtime architecture.
**Requirements**: TURN-CLOSURE-01, TURN-CLOSURE-02, TURN-CLOSURE-03, TURN-CLOSURE-04, TURN-CLOSURE-05, TURN-CLOSURE-06
**Depends on:** Phase 1 turnover-ledger canonical closure/write contracts and Phase 21 formal-relation paired/unpaired visibility contracts. There is no dependency on Phase 25 merely because of numbering.
**Canonical refs:** `.planning/phases/26-oa/26-CONTEXT.md`, `.planning/phases/26-oa/26-RESEARCH.md`, `docs/product-specs/bank-turnover-and-no-oa.md`, `docs/modules/turnover-ledger/boundary-io.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/workbench-relations/boundary-io.md`, `docs/modules/bank-flow-rule-batches/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. Bank-only `turnover_manual_closure` with frozen OA requirement remains one active same-case unpaired relation with missing OA; adding OA moves the same case to paired, while a frozen double-false policy permits direct paired display.
  2. New turnover relations freeze actual selected bank tag codes, canonical rule version/source and OR-composed OA/invoice requirements through the existing helper; unknown/missing inputs fail closed.
  3. Merged closure bank members are a subset of selected bank IDs, selected-row cache covers every policy input with zero additional bank list I/O, and invalid supersets conflict before relation mutation.
  4. The turnover completion bypass, hard-coded metadata and legacy no-OA active-relation resync chain are deleted with no fallback or old runtime references; API/DTO/frontend production code and unrelated relation modes remain unchanged.
  5. Existing repair ops safely repair active legacy-invalid turnover snapshots with metadata-preimage+after-image fingerprint, original-plan reconstruction for audited/idempotent partial execution, and history-based in-place exact metadata rollback; relation members/status/mode/lifecycle/created fields remain unchanged, while Workbench v6 plus existing atomic rehydrate prevents v5 generation/cache from appearing fresh.
  6. Seven-category tests, provider call counts, exact current/previous release evidence, formal readiness/identity/Page/System Audit, controlled dry-run SLO and same-scenario reversible E2E pass; post-execute failure rolls metadata back before previous-release activation/rehydration. The test-owned reversible fixture uses audited fixture recovery and release rollback without creating an additional database backup.

**Plans:** 5 plans

Plans:

- [x] 26-01-PLAN — TDD online root-cause fix, selected-member invariant, real policy snapshot, legacy sync deletion, minimal docs and isolated regression coverage.
- [x] 26-02-PLAN — Historical repair target expansion, Workbench v6 and automatic verification; production dry-run found zero metadata-repair targets but exposed a separate lifecycle dependency loop before final closure.
- [x] 26-03-PLAN — Minimal invoice-lifecycle dependency-scope repair, regression/docs, exact-release deployment, queue drain, affected-page Audit and performance closure.
- [x] 26-04-PLAN — Strict-versus-legacy invoice provenance and ETC imported/closed Audit classification closure.
- [x] 26-05-PLAN — Invoice-page relation relevance Audit closure and restored test-owned Turnover fixture proof.

### Phase 27: 按页面访问收敛 Read Model、消除写后全局 Fan-out 并完成全页面生产验证

**Goal:** Migrate ordinary writes from synchronous cross-page read-model fan-out to canonical commit plus exact access-time freshness convergence, without new runtime infrastructure, while preserving strict correctness, Workbench active generations, explicit batch workflows and full production verification. Latency is measured, but the 3-second stale-to-fresh target is deferred from this phase's completion gate.
**Requirements**: RMF-01, RMF-02, RMF-03, RMF-04, RMF-05, RMF-06, RMF-07, RMF-08, RMF-09
**Depends on:** Phase 26 correctness/frozen-requirement contracts and its controlled production fixture baseline; Phase 27 closes the fan-out performance failures exposed by that baseline.
**Canonical refs:** `.planning/phases/27-read-model-fan-out/27-CONTEXT.md`, `.planning/phases/27-read-model-fan-out/27-RESEARCH.md`, `.planning/phases/27-read-model-fan-out/27-COVERAGE-MATRIX.md`, `docs/app-architecture/pages.md`, `docs/architecture/module-boundaries/read-model-contracts.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`, `docs/operations/runtime-worker-governance.md`
**Success Criteria** (what must be TRUE):

  1. All 17 registered pages, 110 exported POST/PUT/PATCH/DELETE clients, business Drawers/dynamic openers, 15 manifest read models and direct lifecycle/enqueue/barrier sites stay at zero unmapped coverage.
  2. Ordinary fact/rule writes commit canonical facts, audit/idempotency and stable versions without downstream page refresh fan-out; read-like commands never invalidate and explicit batches remain observable durable jobs.
  3. Page route entry/re-entry, query change, browser manual reload, explicit retry and current-page reconcile perform a cheap freshness/version check and enqueue at most one exact-scope job on mismatch; focus/visibility/BFCache/other-page writes produce no business I/O and stale dependencies fail closed.
  4. Existing gateway/queue/worker/CAS boundaries are reused, Workbench keeps active-generation atomic publish, and superseded lifecycle/barrier/fallback paths are deleted rather than retained in parallel.
  5. Seven-category local gates and exact deployed production probes cover every page, operation and writable Drawer, including correctness, isolation, amplification, retry/reload recovery and measured latency. Completion requires eventual fresh canonical payloads within the existing bounded validation timeout, not a hard 3-second result; slower samples are recorded as `performance_follow_up`.

**Plans:** 7 plans

Plans:

- [x] 27-01-PLAN — Freeze the mechanically checked page, operation, Drawer, read-model and legacy-call coverage contract.
- [x] 27-02-PLAN — Prove the architecture vertically on bank-details and cost-statistics fact/rule/batch behavior.
- [x] 27-03-PLAN — Migrate Workbench, bank-flow, batch-accounting and Turnover relation-heavy writes.
- [x] 27-04-PLAN — Migrate pending/input/OA/output invoice-family rules, facts, Drawers and strict consumers.
- [x] 27-05-PLAN — Complete imports, tax, ETC, settings, App Health and minimal page activation behavior.
- [x] 27-06-PLAN — Delete superseded fan-out paths and close all local correctness/performance gates.
- [x] 27-07-PLAN — Candidate A `bef73c4b6` 完成全矩阵后，Candidate B `3b44f08ef` 集中修复验证 evidence gate；最终 production release、fixture recovery、52/52 probes、System Audit 与 runtime convergence 全部闭合。

### Phase 28: 优化成本统计写后完整 Fresh 的访问恢复热路径

**Goal:** Remove repeated full-history Cost statistics proof I/O while a durable exact recovery is already active, so Bank Detail rows remain independently available and global statistics converge with materially lower database contention, without changing writes, fan-out, scope, workers or correctness semantics.
**Requirements:** Performance follow-up from Phase 27; no new product requirement IDs.
**Depends on:** Phase 27 production correctness and isolation closure.
**Canonical refs:** `.planning/phases/28-cost-statistics-recovery-performance/28-01-PLAN.md`, `docs/modules/cost-statistics/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Cost `time|bank_tag` retries use a lightweight durable active-recovery gate while Workbench/Cost recovery is pending or processing; the full statistics proof only runs when no known recovery is active.
  2. Bank Detail rows remain independently fresh, statistics remain fail closed, and exact scope/zero write fan-out contracts do not change.
  3. Targeted local gates and one production candidate prove correctness, isolation, queue/worker drain and a material improvement over the 7.432-second baseline.

**Plans:** 1 plan

Plans:

- [x] 28-01-PLAN — Add the Cost active-recovery fast gate, run targeted regression, and close production performance/correctness proof (`d8e4c5946`, corrective root fix `b6e814b05`).

### Phase 29: 优化关联台写后和页面访问的完整 Fresh 热路径

**Goal:** Remove repeated full Workbench payload polling during active recovery and reuse the existing lightweight freshness port for public status checks, without changing canonical writes, exact scopes, active-generation publication or cross-page isolation.
**Requirements:** Performance follow-up from Phase 27; no new product requirement IDs.
**Depends on:** Phase 28 production closure and Phase 27 Workbench correctness/isolation contracts.
**Canonical refs:** `.planning/phases/29-workbench-access-performance/29-01-PLAN.md`, `docs/modules/reconciliation-workbench/boundary-io.md`, `docs/modules/read-models/boundary-io.md`, `docs/modules/runtime-workers/boundary-io.md`
**Success Criteria** (what must be TRUE):

  1. Operation recovery performs at most one initial trigger load and one final fresh payload load; active waiting uses the existing lightweight refresh-status boundary.
  2. Canonical source proof remains fail closed, active generations remain atomic, and write-time zero fan-out/exact-scope contracts do not change.
  3. Targeted local gates and one production candidate prove correct confirm/withdraw recovery, reduced access I/O, runtime drain and no unrelated page I/O.

**Plans:** 1 plan

Plans:

- [x] 29-01-PLAN — Reuse lightweight Workbench status, remove repeated full payload polling, and close production performance/correctness proof (`6ec4bc48a`, SQL root fix `f06711b7a`).

---
