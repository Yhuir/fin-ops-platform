# Roadmap: fin-ops-platform Page Analysis

## Overview

This roadmap preserves a single global codebase map while creating isolated GSD phases for each target page. Each page phase should capture discussion context, research findings, implementation risks, test strategy, and executable plans inside its own phase directory.

## Phases

**Phase Numbering:**

- Integer phases (1-17): Page-specific analysis and planning work for every registered app page.
- Decimal phases (2.1, 2.2): Urgent insertions between existing phases.

## Phase Details

### Phase 1: 完善外部往来款管理页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the external turnover ledger page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-01, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
**Canonical refs:** `docs/modules/etc-tickets/README.md`, `docs/modules/etc-tickets/state-machine.md`, `docs/modules/etc-tickets/tests.md`, `web/src/pages/EtcTicketManagementPage.tsx`, `web/src/features/etc/api.ts`, `backend/src/fin_ops_platform/app/routes_etc.py`, `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`, `backend/src/fin_ops_platform/services/etc_service.py`
**Success Criteria** (what must be TRUE):
  1. Phase artifacts identify etc-tickets module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.
**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 12 to break down)

### Phase 13: 完善设置页面：分析现状、风险、功能缺口和实施计划

**Goal:** Capture the settings page's current module facts, code entry points, risks, feature gaps, and executable improvement plan in this phase directory.
**Requirements**: PAGE-15, PAGE-04, PAGE-05, PAR-01, PAR-02, PAR-03
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
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
**Depends on:** Global `.planning/codebase/` map; no page phase dependency.
**Canonical refs:** `docs/modules/imports-etc-invoices/README.md`, `docs/modules/imports-etc-invoices/state-machine.md`, `docs/modules/imports-etc-invoices/tests.md`, `web/src/pages/imports/ImportEtcInvoicesPage.tsx`, `web/src/components/imports/ImportWorkflowPage.tsx`, `web/src/features/etc/api.ts`, `backend/src/fin_ops_platform/services/etc_service.py`, `backend/src/fin_ops_platform/services/import_processing_service.py`, `backend/src/fin_ops_platform/services/import_job_queue.py`
**Success Criteria** (what must be TRUE):
  1. Phase artifacts identify imports-etc-invoices module docs, frontend/backend entry points, read model/worker boundaries, cross-page impacts, and verification commands.
  2. Any implementation plan preserves `.planning/codebase/` as the global map and writes page-specific analysis only inside this phase directory.
  3. Tests and docs impact assessment are explicitly mapped before implementation starts.
**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 17 to break down)

---

## Progress

**Execution Order:**
The page-analysis phases can run independently in separate worktree threads. Merge planning artifacts carefully if multiple threads update shared root planning files.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
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
| 12. ETC票据管理 | 0/0 | Not started | - |
| 13. 设置 | 0/0 | Not started | - |
| 14. 系统状态 | 0/0 | Not started | - |
| 15. 银行流水导入 | 0/0 | Not started | - |
| 16. 发票导入 | 0/0 | Not started | - |
| 17. ETC发票导入 | 0/0 | Not started | - |

---
