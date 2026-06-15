# Roadmap: fin-ops-platform Page Analysis

## Overview

This roadmap preserves a single global codebase map while creating isolated GSD phases for each target page. Each page phase should capture discussion context, research findings, implementation risks, test strategy, and executable plans inside its own phase directory.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Page-specific analysis and planning work.
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

---

## Progress

**Execution Order:**
The three page-analysis phases can run independently in separate worktree threads. Merge planning artifacts carefully if multiple threads update shared root planning files.

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. 外部往来款管理 | 0/0 | Not started | - |
| 2. 银行明细 | 0/0 | Not started | - |
| 3. 税金抵扣 | 0/0 | Not started | - |

---
