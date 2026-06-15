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

## v2 Requirements

### Automation

- **AUTO-01**: Add a reusable helper command or template for creating future page-analysis phases.
- **AUTO-02**: Add a lint/check to warn when page-analysis threads modify `.planning/codebase/*.md`.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Business implementation changes | This step only creates planning structure. |
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

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-06-16*
*Last updated: 2026-06-16 after adding Phase 0 cross-page dependency baseline*
