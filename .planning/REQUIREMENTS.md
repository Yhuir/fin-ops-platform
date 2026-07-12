# Requirements: fin-ops-platform Page Analysis Phases

**Defined:** 2026-06-16
**Core Value:** Preserve production finance workflow correctness while improving individual pages through isolated, reviewable GSD phases.

## v1 Requirements

### Page-Scoped Planning

- [ ] **BASE-00**: A cross-page dependency baseline is completed before any page implementation work starts.
- [ ] **PAGE-01**: External turnover ledger page analysis is stored in its own phase artifacts.
- [ ] **PAGE-02**: Bank details page analysis is stored in its own phase artifacts.
- [ ] **PAGE-03**: Tax offset page analysis is stored in its own phase artifacts.
- [ ] **PAGE-04**: The global `.planning/codebase/` map is not overwritten by page-specific analysis.
- [ ] **PAGE-05**: Each page phase records module docs, code entry points, risks, and verification strategy before implementation.
- [ ] **PAGE-06**: Reconciliation workbench page analysis is stored in its own phase artifacts.
- [ ] **PAGE-07**: Cost statistics page analysis is stored in its own phase artifacts.
- [ ] **PAGE-08**: Pending invoices page analysis is stored in its own phase artifacts.
- [ ] **PAGE-09**: Input invoice usage page analysis is stored in its own phase artifacts.
- [ ] **PAGE-10**: OA pending payments page analysis is stored in its own phase artifacts.
- [ ] **PAGE-11**: Output invoice collections page analysis is stored in its own phase artifacts.
- [ ] **PAGE-12**: No-OA bank batches page analysis is stored in its own phase artifacts.
- [ ] **PAGE-13**: Batch accounting page analysis is stored in its own phase artifacts.
- [ ] **PAGE-14**: ETC tickets page analysis is stored in its own phase artifacts.
- [ ] **PAGE-15**: Settings page analysis is stored in its own phase artifacts.
- [ ] **PAGE-16**: App Health operations page analysis is stored in its own phase artifacts.
- [ ] **PAGE-17**: Bank transaction import page analysis is stored in its own phase artifacts.
- [ ] **PAGE-18**: Invoice import page analysis is stored in its own phase artifacts.
- [ ] **PAGE-19**: ETC invoice import page analysis is stored in its own phase artifacts.

### Parallel Work Safety

- [ ] **PAR-01**: Parallel Codex threads operate in separate worktrees or otherwise avoid overlapping write targets.
- [ ] **PAR-02**: Each page thread only writes its assigned phase directory unless explicitly asked to update long-term docs.
- [ ] **PAR-03**: Long-term facts discovered during analysis are promoted to `docs/modules/<module>/` only after review.

### Page Audit Proof Closure

- [ ] **AUDIT-01**: Every page registered in `web/src/app/pageRegistry.tsx` has an explicit fail-closed Audit contract or an explicit non-read-model operational proof contract.
- [ ] **AUDIT-02**: Every page Audit compares an independently owned canonical expected set with the complete page projection in both directions.
- [ ] **AUDIT-03**: Every page Audit independently recalculates all registered business-critical display fields and summary totals.
- [ ] **AUDIT-04**: Canonical relation edges, shared `workbench_relation` edges, Workbench active-generation edges, and every page consumer projection are equal in both directions.
- [ ] **AUDIT-05**: Audit results are produced from one system-level repeatable-read read-only snapshot and bind the current audit/source/read-model/relation/config/generation versions.
- [ ] **AUDIT-06**: Freshness, queue and readiness use one manifest-driven current-effective policy across Audit, App Status, operation barriers and SLO smoke.
- [ ] **AUDIT-07**: `fan_out_command/all` historical readiness is diagnostic-only while current dirty/outbox failures remain blocking; queryable parent readiness remains blocking.
- [ ] **AUDIT-08**: External source completeness is reported separately and cannot pass when required control evidence is absent.
- [ ] **AUDIT-09**: Specialized and parallel legacy Audit runtime paths are removed after callers migrate, with static guards preventing reintroduction.
- [ ] **AUDIT-10**: The exact cross-page omitted-relation counterexample fails deterministically and all applicable seven-category tests pass.
- [ ] **AUDIT-11**: Any required read-model rebuild uses the formal refresh gateway and durable queue with staged drain, idempotency, rollback and no direct SQL mark-fresh.
- [ ] **AUDIT-12**: Production closure proves release consistency, worker/queue convergence, all-page system Audit, version currency and legacy-route absence using read-only evidence after authorized deployment.

### Reversible Relation Closure

- [ ] **RELCL-01**: Controlled relation scenarios use one existing runner and one canonical Workbench relation write boundary; no second fact, queue, freshness or Audit owner is introduced.
- [ ] **RELCL-02**: Every confirm and withdraw checkpoint independently proves all required fan-out scopes, worker completion and freshness from post-mutation durable evidence.
- [ ] **RELCL-03**: Every checkpoint obtains a new fail-closed App Health System Audit report with integrity pass, freshness fresh, queue drained and all registered internal page proofs passing.
- [ ] **RELCL-04**: Bank+invoice, bank+turnover and bank+OA+invoice are covered as data-driven reversible shapes without 17×operation duplication.
- [ ] **RELCL-05**: Affected consumer API/Browser contracts prove user-visible relation results while non-consumers remain isolated.
- [ ] **RELCL-06**: Legacy/parallel runners, direct derived-data writes and mock-only closure claims are removed after whole-repo caller evidence; retained operational adapters are explicit.
- [ ] **RELCL-07**: Real-infrastructure execution is restricted to disposable/test-owned fixtures with auth, admin Audit access, approval, rollback and cleanup gates.

## v2 Requirements

### Automation

- **AUTO-01**: Add a reusable helper command or template for creating future page-analysis phases.
- **AUTO-02**: Add a lint/check to warn when page-analysis threads modify `.planning/codebase/*.md`.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Business changes unrelated to Audit/readiness closure | The milestone remains page-scoped; Phase 19 authorizes only the cross-page proof and runtime consistency work defined by AUDIT-01..12. |
| Full project roadmap redesign | The immediate goal is page-scoped phase scaffolding. |
| Per-page copies of the seven codebase map files | They duplicate global map semantics and create merge conflicts. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BASE-00 | Phase 0 | Pending |
| PAGE-01 | Phase 1 | Pending |
| PAGE-02 | Phase 2 | Pending |
| PAGE-03 | Phase 3 | Pending |
| PAGE-04 | Phase 0-17 | Pending |
| PAGE-05 | Phase 0-17 | Pending |
| PAGE-06 | Phase 4 | Pending |
| PAGE-07 | Phase 5 | Pending |
| PAGE-08 | Phase 6 | Pending |
| PAGE-09 | Phase 7 | Pending |
| PAGE-10 | Phase 8 | Pending |
| PAGE-11 | Phase 9 | Pending |
| PAGE-12 | Phase 10 | Pending |
| PAGE-13 | Phase 11 | Pending |
| PAGE-14 | Phase 12 | Pending |
| PAGE-15 | Phase 13 | Pending |
| PAGE-16 | Phase 14 | Pending |
| PAGE-17 | Phase 15 | Pending |
| PAGE-18 | Phase 16 | Pending |
| PAGE-19 | Phase 17 | Pending |
| PAR-01 | Phase 0-17 | Pending |
| PAR-02 | Phase 0-17 | Pending |
| PAR-03 | Phase 0-17 | Pending |
| AUDIT-01 | Phase 19 | Pending |
| AUDIT-02 | Phase 19 | Pending |
| AUDIT-03 | Phase 19 | Pending |
| AUDIT-04 | Phase 19 | Pending |
| AUDIT-05 | Phase 19 | Pending |
| AUDIT-06 | Phase 19 | Pending |
| AUDIT-07 | Phase 19 | Pending |
| AUDIT-08 | Phase 19 | Pending |
| AUDIT-09 | Phase 19 | Pending |
| AUDIT-10 | Phase 19 | Pending |
| AUDIT-11 | Phase 19 | Pending |
| AUDIT-12 | Phase 19 | Pending |
| RELCL-01 | Phase 20 | Pending |
| RELCL-02 | Phase 20 | Pending |
| RELCL-03 | Phase 20 | Pending |
| RELCL-04 | Phase 20 | Pending |
| RELCL-05 | Phase 20 | Pending |
| RELCL-06 | Phase 20 | Pending |
| RELCL-07 | Phase 20 | Pending |

**Coverage:**
- v1 requirements: 42 total
- Mapped to phases: 42
- Unmapped: 0

---
*Requirements defined: 2026-06-16*
*Last updated: 2026-07-11 after adding Phase 19 Audit proof closure requirements*
