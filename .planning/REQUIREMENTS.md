# Requirements: fin-ops-platform Page Analysis Phases

**Defined:** 2026-06-16
**Core Value:** Preserve production finance workflow correctness while improving individual pages through isolated, reviewable GSD phases.

## v1 Requirements

### Page-Scoped Planning

- [ ] **BASE-00**: A cross-page dependency baseline is completed before any page implementation work starts.
- [ ] **PAGE-01**: External turnover ledger page analysis is stored in its own phase artifacts.
- [ ] **PAGE-02**: Bank details page analysis is stored in its own phase artifacts.
- [ ] **PAGE-03**: Tax offset page analysis is stored in its own phase artifacts.
- [x] **PAGE-04**: The global `.planning/codebase/` map is not overwritten by page-specific analysis.
- [x] **PAGE-05**: Each page phase records module docs, code entry points, risks, and verification strategy before implementation.
- [ ] **PAGE-06**: Reconciliation workbench page analysis is stored in its own phase artifacts.
- [ ] **PAGE-07**: Cost statistics page analysis is stored in its own phase artifacts.
- [ ] **PAGE-08**: Pending invoices page analysis is stored in its own phase artifacts.
- [ ] **PAGE-09**: Input invoice usage page analysis is stored in its own phase artifacts.
- [ ] **PAGE-10**: OA pending payments page analysis is stored in its own phase artifacts.
- [ ] **PAGE-11**: Output invoice collections page analysis is stored in its own phase artifacts.
- [ ] **PAGE-12**: No-OA bank batches page analysis is stored in its own phase artifacts.
- [ ] **PAGE-13**: Batch accounting page analysis is stored in its own phase artifacts.
- [x] **PAGE-14**: ETC tickets page analysis is stored in its own phase artifacts.
- [ ] **PAGE-15**: Settings page analysis is stored in its own phase artifacts.
- [ ] **PAGE-16**: App Health operations page analysis is stored in its own phase artifacts.
- [ ] **PAGE-17**: Bank transaction import page analysis is stored in its own phase artifacts.
- [ ] **PAGE-18**: Invoice import page analysis is stored in its own phase artifacts.
- [ ] **PAGE-19**: ETC invoice import page analysis is stored in its own phase artifacts.

### Parallel Work Safety

- [x] **PAR-01**: Parallel Codex threads operate in separate worktrees or otherwise avoid overlapping write targets.
- [x] **PAR-02**: Each page thread only writes its assigned phase directory unless explicitly asked to update long-term docs.
- [x] **PAR-03**: Long-term facts discovered during analysis are promoted to `docs/modules/<module>/` only after review.

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

- [x] **RELCL-01**: Controlled relation scenarios use one existing runner and one canonical Workbench relation write boundary; no second fact, queue, freshness or Audit owner is introduced.
- [x] **RELCL-02**: Every confirm and withdraw checkpoint independently proves all required fan-out scopes, worker completion and freshness from post-mutation durable evidence.
- [x] **RELCL-03**: Every checkpoint obtains a new fail-closed App Health System Audit report with integrity pass, freshness fresh, queue drained and all registered internal page proofs passing.
- [x] **RELCL-04**: Bank+invoice, bank+turnover and bank+OA+invoice are covered as data-driven reversible shapes without 17×operation duplication.
- [x] **RELCL-05**: Affected consumer API/Browser contracts prove user-visible relation results while non-consumers remain isolated.
- [x] **RELCL-06**: Legacy/parallel runners, direct derived-data writes and mock-only closure claims are removed after whole-repo caller evidence; retained operational adapters are explicit.
- [x] **RELCL-07**: Real-infrastructure execution is restricted to disposable/test-owned fixtures with auth, admin Audit access, approval, rollback and cleanup gates.

### Workbench Deterministic Relation Visibility Closure

- [x] **RELVIS-01**: Every eligible canonical Workbench fact appears exactly once: as a member of one active formal relation or as one standalone unpaired row; no fact is hidden or duplicated.
- [ ] **RELVIS-02**: A deterministic safe automatic match creates or extends the canonical active relation in the same orchestration path; candidate/proposed/open/paired decision records are not persisted or exposed as business relation state.
- [ ] **RELVIS-03**: Matching supports cross-month OA, bank and invoice facts and arbitrary N:M:K cardinality without a business-size cap, while computation remains bounded and fails closed.
- [ ] **RELVIS-04**: Amount-only, fuzzy-only, date-only, ambiguous, conflicting, resource-limited and unsafe negative/refund results never create a formal relation; their facts remain visible as standalone unpaired rows.
- [ ] **RELVIS-05**: Legacy candidate-match and reconciliation-decision runtime paths, projection hooks, repository filters, frontend states, tests and database objects are removed after a whole-repository caller scan; no compatibility fallback remains on the new chain.
- [ ] **RELVIS-06**: Existing active relations remain unchanged and visible regardless of historical group-id prefix or creation origin; relations persist until an explicit audited withdraw/cancel, and an explicit withdrawal blocks automatic recreation of the same row set.
- [ ] **RELVIS-07**: `month=all` composes the union of every active month shard by canonical member identity and cannot drop source-linked or otherwise repeated group members; list, detail and Audit use the same generation boundary.
- [x] **RELVIS-08**: Relation writes use `WorkbenchRelationCommandService`/UoW, SQL remains in repositories, matching is pure over bulk inputs, and read-model refresh uses the existing gateway/durable queue with no page/route/service/repository/worker I/O pollution.
- [ ] **RELVIS-09**: The forward migration deletes only retired derived candidate/decision state, never creates or rewrites canonical facts or pre-existing active relations, and is followed by registered read-model rehydration plus before/after hash and count verification.
- [ ] **RELVIS-10**: Applicable seven-category tests and controlled data verification prove the Yunnan Lifu 520 invoice/OA relation is paired, the known 13 omitted invoices are recovered as unpaired, queues/read models converge, and canonical data is unchanged.

### Turnover Closure Frozen Requirement Correctness

- [x] **TURN-CLOSURE-01**: A `turnover_manual_closure` active relation represents canonical member ownership only; it enters Workbench paired only when its frozen OA/invoice requirements are complete, otherwise it remains one same-case unpaired relation with explicit missing row types.
- [x] **TURN-CLOSURE-02**: Turnover closure confirmation reuses the existing Bank Transaction Paired Policy helper to freeze actual selected bank tag codes, rule version, source and OA/invoice requirements; multi-tag requirements use OR and unknown/missing inputs fail closed.
- [x] **TURN-CLOSURE-03**: Every bank member in a merged turnover closure is contained in the current selected bank IDs, selected-row cache covers all policy inputs with no additional bank list I/O, and the hard-coded requirement path plus legacy no-OA relation resync chain are fully removed without fallback.
- [x] **TURN-CLOSURE-04**: Existing repair ops identify active turnover relations with non-canonical requirement source or missing canonical tag/version metadata and rebuild them from fresh tags/rules; forward fingerprint binds exact metadata preimage plus intended after image, partial replay rebuilds the original plan from fresh targets plus fingerprint histories, and rollback verifies every current after image before the first write then precisely replaces only `special_metadata` with its recorded preimage through the canonical audited/idempotent metadata-update UoW without cancel/recreate or ownership/lifecycle/created-field changes; drift is zero-write, rollback reaches target zero, ordinary missing-snapshot compatibility and ETC/batch exemptions remain unchanged.
- [x] **TURN-CLOSURE-05**: Workbench month/all schema is upgraded from v5 to v6 so old generations and derived caches fail closed; an exact uploaded release uses captured previous release, authorized atomic rehydrate, formal readiness/Audit evidence and a post-execute failure sequence of exact metadata rollback before previous-release activation/rehydration. The test-owned reversible fixture relies on audited fixture recovery plus release rollback and does not require an additional database backup.
- [x] **TURN-CLOSURE-06**: Applicable seven-category tests, provider I/O counts, old-symbol zero-reference guards, minimal docs, controlled dry-run SLO checks and same-scenario test-owned reversible E2E compare previous/new releases under explicit safety ceilings without changing API/DTO/frontend production components or adding tables, workers, read models, runtime services/repositories/helpers or dependencies.

### Access-Time Read Model Freshness And Fan-out Elimination

- [x] **RMF-01**: Every current registered page, manifest read model, mutating frontend API, writable Drawer/dynamic panel, non-page dependency and direct lifecycle/enqueue site is mapped to one owner, exact I/O contract, migration action, deletion condition and test owner; all unmapped counts are zero before runtime edits begin.
- [x] **RMF-02**: Ordinary commands atomically commit only canonical facts, exact source versions and audit/idempotency state, return within the write SLO, and create no downstream page refresh jobs or global operation-barrier wait.
- [x] **RMF-03**: Route entry/re-entry, business-scope/query change, browser manual reload, explicit retry and current-page post-mutation reconciliation use the existing freshness/status/enqueue boundary; focus/visibility/BFCache/another-page writes produce zero business page I/O; fresh scopes do no work and stale dependencies enqueue at most one current-effective job per model/scope/target version.
- [x] **RMF-04**: All migrated workers rebuild only validated exact scopes, preserve Workbench active-generation semantics, publish atomically with source-version CAS, coalesce moving targets and recover from restart without stale overwrite, per-row jobs or new infrastructure.
- [x] **RMF-05**: Every writable Drawer is classified as canonical fact, projection-semantic rule, read-time/display rule or explicit batch; read-only Drawers remain query-only, and no Drawer save/open can trigger unrelated page work or cross-page I/O.
- [x] **RMF-06**: All superseded write-time lifecycle fan-out, bare-all fallback, direct queue I/O, global barrier wait, page-cross-read and live/legacy fallback paths are removed per vertical slice with whole-repository zero-reference guards and no hidden dual path.
- [x] **RMF-07**: Applicable seven-category tests plus deterministic/disposable PostgreSQL integration prove permissions, audit, idempotency, rollback, fresh/stale/202/409 contracts, queue dedupe, CAS, route/manual-reload recovery, browser-lifecycle zero I/O, exports and unrelated-page isolation across all registered pages and operations.
- [x] **RMF-08**: Reference-data performance records ordinary command, freshness gate, already-fresh payload and access-to-fresh timings without treating the 3-second SLO as this phase's hard gate; correctness, bounded/recoverable loading, zero fan-out and unrelated I/O isolation remain mandatory.
- [ ] **RMF-09**: After all local release gates pass, the exact changes are committed and pushed to remote main, deployed through the official production entry, and verified in production for every page, operation and writable Drawer with latency, freshness, job amplification, unrelated-page deltas, System Audit and rollback evidence; any failure re-enters the fix/release loop.

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
| PAGE-04 | Phase 0-17 | Complete |
| PAGE-05 | Phase 0-17 | Complete |
| PAGE-06 | Phase 4 | Pending |
| PAGE-07 | Phase 5 | Pending |
| PAGE-08 | Phase 6 | Pending |
| PAGE-09 | Phase 7 | Pending |
| PAGE-10 | Phase 8 | Pending |
| PAGE-11 | Phase 9 | Pending |
| PAGE-12 | Phase 10 | Pending |
| PAGE-13 | Phase 11 | Pending |
| PAGE-14 | Phase 12 | Complete |
| PAGE-15 | Phase 13 | Pending |
| PAGE-16 | Phase 14 | Pending |
| PAGE-17 | Phase 15 | Pending |
| PAGE-18 | Phase 16 | Pending |
| PAGE-19 | Phase 17 | Pending |
| PAR-01 | Phase 0-17 | Complete |
| PAR-02 | Phase 0-17 | Complete |
| PAR-03 | Phase 0-17 | Complete |
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
| RELCL-01 | Phase 20 | Complete |
| RELCL-02 | Phase 20 | Complete |
| RELCL-03 | Phase 20 | Complete |
| RELCL-04 | Phase 20 | Complete |
| RELCL-05 | Phase 20 | Complete |
| RELCL-06 | Phase 20 | Complete |
| RELCL-07 | Phase 20 | Complete |
| RELVIS-01 | Phase 21 | Complete |
| RELVIS-02 | Phase 21 | Pending |
| RELVIS-03 | Phase 21 | Pending |
| RELVIS-04 | Phase 21 | Pending |
| RELVIS-05 | Phase 21 | Pending |
| RELVIS-06 | Phase 21 | Pending |
| RELVIS-07 | Phase 21 | Pending |
| RELVIS-08 | Phase 21 | Complete |
| RELVIS-09 | Phase 21 | Pending |
| RELVIS-10 | Phase 21 | Pending |
| TURN-CLOSURE-01 | Phase 26 | Complete |
| TURN-CLOSURE-02 | Phase 26 | Complete |
| TURN-CLOSURE-03 | Phase 26 | Complete |
| TURN-CLOSURE-04 | Phase 26 | Complete |
| TURN-CLOSURE-05 | Phase 26 | Complete |
| TURN-CLOSURE-06 | Phase 26 | Complete |
| RMF-01 | Phase 27 | Complete |
| RMF-02 | Phase 27 | Complete |
| RMF-03 | Phase 27 | Complete |
| RMF-04 | Phase 27 | Complete |
| RMF-05 | Phase 27 | Complete |
| RMF-06 | Phase 27 | Complete |
| RMF-07 | Phase 27 | Complete |
| RMF-08 | Phase 27 | Complete |
| RMF-09 | Phase 27 | Pending |

**Coverage:**

- v1 requirements: 67 total
- Mapped to phases: 67
- Unmapped: 0

---
*Requirements defined: 2026-06-16*
*Last updated: 2026-07-25 after reconciling completed Phase 26 and Phase 27 local release evidence; RMF-09 remains production-gated*
