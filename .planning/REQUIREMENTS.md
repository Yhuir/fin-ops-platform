# Requirements: fin-ops-platform Page Analysis Phases

**Defined:** 2026-06-16
**Core Value:** Preserve production finance workflow correctness while improving individual pages through isolated, reviewable GSD phases.

## v1 Requirements

### Page-Scoped Planning

- [ ] **PAGE-01**: External turnover ledger page analysis is stored in its own phase artifacts.
- [ ] **PAGE-02**: Bank details page analysis is stored in its own phase artifacts.
- [ ] **PAGE-03**: Tax offset page analysis is stored in its own phase artifacts.
- [ ] **PAGE-04**: The global `.planning/codebase/` map is not overwritten by page-specific analysis.
- [ ] **PAGE-05**: Each page phase records module docs, code entry points, risks, and verification strategy before implementation.

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
| PAGE-01 | Phase 1 | Pending |
| PAGE-02 | Phase 2 | Pending |
| PAGE-03 | Phase 3 | Pending |
| PAGE-04 | Phase 1, Phase 2, Phase 3 | Pending |
| PAGE-05 | Phase 1, Phase 2, Phase 3 | Pending |
| PAR-01 | Phase 1, Phase 2, Phase 3 | Pending |
| PAR-02 | Phase 1, Phase 2, Phase 3 | Pending |
| PAR-03 | Phase 1, Phase 2, Phase 3 | Pending |

**Coverage:**
- v1 requirements: 8 total
- Mapped to phases: 8
- Unmapped: 0

---
*Requirements defined: 2026-06-16*
*Last updated: 2026-06-16 after initializing page-scoped GSD phase structure*
