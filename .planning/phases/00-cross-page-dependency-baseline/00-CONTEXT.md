# Phase 0: Cross-Page Dependency Baseline - Context

**Gathered:** 2026-06-16
**Status:** Complete
**Source:** Direct repository and documentation analysis

<domain>
## Phase Boundary

Phase 0 establishes the cross-page baseline required before page implementation work starts. It covers all app registry pages, page dependencies, backend lifecycle fan-out, read model/worker ownership, App Status bindings, legacy entry points, risk gates, testing obligations, docs impact, and recommended implementation order.

It does not implement product behavior and does not replace page-specific phases. It tells each downstream page phase what must be checked before implementation.
</domain>

<decisions>
## Locked Decisions

### Baseline First

- Every page implementation phase must read Phase 0 before writing a page-level plan.
- Page implementation does not require all 17 pages to have deep `PLAN.md` files up front.
- Page implementation does require this L1 cross-page baseline plus L2 page-level analysis for the selected page or strongly coupled page group.

### Planning Isolation

- `.planning/codebase/` remains the global repository map.
- Page-specific analysis belongs in `.planning/phases/<phase>/`.
- Phase 0 may be referenced by all page phases, but page phases should avoid rewriting Phase 0 unless a baseline fact is wrong or stale.

### Cross-Page Safety

- A page is not a safe implementation unit until its upstream writes, downstream readers, read models, workers, stale/fresh states, cache invalidation, operation-barrier behavior, exports, and regression tests are mapped.
- Frontend domain events are refresh hints only. Durable consistency must be expressed through backend lifecycle, dirty scopes, outbox, read model refresh, worker readiness, and operation barriers.
- Any write that changes canonical facts or cross-page read models must separate "write committed" from "page safe to continue" using affected scopes and freshness/barrier checks.

### Legacy Cleanup

- Old logic must not be allowed to keep polluting active data paths.
- Deletion is allowed only after the page phase classifies the old path as dead or transitional, migrates callers to the canonical boundary, adds tests for the canonical path, verifies no active callers remain, and removes stale docs/tests/references.
- Unknown legacy paths are blockers, not deletion candidates.

### Architecture Gate

- Routes should map HTTP contracts and permissions.
- Business rules belong in services.
- SQL details belong in repositories/projections.
- Workers must not depend on HTTP/Application/session state.
- Read model refresh requests must pass through gateway/policy/registry boundaries before durable queue writes.
- `workbench` remains an active-generation model and must not be mechanically forced into a generic read model pattern.

### Tests And Docs

- Each page phase must evaluate the repository's seven test categories.
- Existing test entry points must be listed before implementation.
- Docs impact assessment is mandatory for any page, API, read model, worker, permission, audit, export, state, or data-flow change.
</decisions>

<canonical_refs>
## Canonical References

Downstream agents must read the relevant subset before planning or implementation:

- `AGENTS.md` - repository instructions and read model/worker governance rules.
- `docs/app-architecture/pages.md` - current page grouping, page responsibilities, frontend events, and cross-page impact.
- `docs/app-architecture/runtime-and-ownership.md` - runtime call chain, write/read boundaries, operation barrier, worker/queue/App Status model.
- `docs/modules/README.md` - module index and per-module documentation requirements.
- `docs/modules/read-models/README.md` - read model freshness, gateway, dirty scope, and operation-barrier boundaries.
- `docs/modules/runtime-workers/README.md` - runtime worker boundaries and registry requirements.
- `docs/modules/domain-events-lifecycle/README.md` - frontend event vs backend lifecycle boundary.
- `docs/modules/permissions-and-audit/README.md` - permission levels, audit expectations, and sensitive-data constraints.
- `docs/dev/testing.md` - verification commands and testing closure rules.
- `docs/dev/testing-closure-dependency-map.md` - page/API/read model/worker/test ownership map.
- `web/src/app/pageRegistry.tsx` - registered pages and routes.
- `web/src/features/domainEvents.ts` - frontend finance domain events.
- `backend/src/fin_ops_platform/services/derived_data_lifecycle_service.py` - backend lifecycle event to derived domain fan-out.
- `backend/src/fin_ops_platform/services/app_status_domain_registry.py` - page domain to read model/worker/job/dependency bindings.
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py` - read model readiness registry.
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py` - worker instance/event registry.
</canonical_refs>

<specifics>
## Baseline-Specific Implementation Rules

- A page phase must cite the upstream/downstream rows from `PAGE-DEPENDENCY-MATRIX.md`.
- A page phase must cite affected read models/workers from `READ-MODEL-WORKER-MATRIX.md`.
- A page phase must cite relevant lifecycle events from `CROSS-PAGE-DATAFLOW.md`.
- A page phase must complete the legacy cleanup gate from `LEGACY-ENTRYPOINTS.md` before deleting old code.
- If a page phase touches shared import workflow, Workbench relation facts, invoice lifecycle, App Status, settings reset, or operation barrier, it must plan cross-page regression tests rather than page-only tests.
</specifics>

<deferred>
## Deferred Ideas

- Automate drift checks that compare `pageRegistry.tsx`, App Status domain registry, read model registry, worker registry, and `docs/modules/README.md`.
- Add a GSD guard that warns when page phases edit `.planning/codebase/*.md`.
- Add a generated page dependency diagram once the implementation order stabilizes.
</deferred>
