# Batch Accounting Module Closure Audit And Production Evidence Defer

**Date:** 2026-06-24
**Boundary:** `batch-accounting:module-closure-audit-and-production-evidence-defer`
**Status:** production evidence deferred; module not fully closed

## Scope

Audit whether `batch-accounting` can be considered locally closed after:

- GET route owner extraction;
- submit/withdraw route side-effect port extraction;
- app-level repair helper removal;
- existing service command-boundary and read model/freshness tests.

This slice does not change runtime behavior.

## Closure Criteria

| Requirement | Evidence | Result |
| --- | --- | --- |
| IO contract | `docs/modules/batch-accounting/README.md`, state-machine/tests/implementation notes, analysis files | locally satisfied |
| Public/internal boundary | `BatchAccountingApiRoutes` owns route DTO/error mapping; `BatchAccountingService` owns business rules; `server.py` keeps session/JSON/response mapping | locally satisfied |
| Canonical fact owner | Relation facts owned by `WorkbenchRelationCommandService` / relation repository; batch-accounting is not an independent fact source | locally satisfied |
| Shared fact source | `workbench_relation` remains the shared distribution/read model source | locally satisfied |
| Read model contract | GET uses `BatchAccountingService.build_payload(..., use_sql_read_model=True)` and relation facade freshness; tests cover missing/stale/non-fresh diagnostics | locally satisfied |
| Force refresh contract | No independent batch-accounting read model; force refresh is not module-specific. Related refresh enters via `workbench_relation` lifecycle/gateway/operation barrier | not-applicable locally |
| Operation barrier | Frontend tests and E2E docs cover submit/withdraw waiting for `workbench_relation` barrier before reload/overlay release | locally satisfied |
| Legacy removal/quarantine | `Application._repair_batch_accounting_relation_case_ids(...)` removed; GET cannot repair/write/schedule; route owner guards prevent direct relation writes | locally satisfied |
| Permission contract | Mutation routes still require `_batch_accounting_mutation_session(...)`; module docs record permission behavior | locally satisfied |
| Audit contract | Relation command/history metadata and lifecycle metadata remain service/command-owned; no route-level audit semantics changed | locally satisfied |
| Test contract | API, service, route guard, read model/facade, worker registry, frontend and E2E tests are documented in `docs/modules/batch-accounting/tests.md` | locally satisfied |
| Docs updates | Module docs and backend-refactor docs updated through the preceding slices | locally satisfied |
| Environment evidence | No local `PGSQL_URL`; no staging database; no production controlled write or worker drain executed | deferred |

## Decision

Do not mark `batch-accounting` as fully `closed`.

Mark the autonomous slice as `production-evidence-deferred` and the module closure as `not-module-closed`, because the remaining evidence requires real PostgreSQL/worker/runtime data that is unavailable locally and cannot be replaced with staging.

This is not a hard blocker:

- no production write is required for the current refactor slice;
- no secret is required;
- the missing evidence is explicitly tracked;
- the autonomous workflow can continue to the next non-Go implementation/foundation boundary.

## Missing Evidence

- Real production `workbench_relation` dirty/outbox/readiness behavior after batch-accounting submit/withdraw.
- Real worker drain and App Status convergence for affected months.
- Real historical batch relation/case-id collision dataset dry-run.
- Real high-row-count year/browser performance and overlay flow under production data.

## Why Not Use PGSQL_URL Or Staging

The user stated there is no local `PGSQL_URL` and no staging database. The refactor plan must not depend on either.

Therefore the only acceptable handling is:

- use local deterministic unit/API/static/frontend evidence for implementation closure;
- record real database/worker evidence as `production-evidence-deferred`;
- require future production validation to be read-only unless a separate human-approved controlled write/rollback runbook exists.

## State Machine Impact

- Global workflow definition: unchanged.
- Module state definition: unchanged.
- Reviewed files:
  - `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
  - `docs/modules/batch-accounting/state-machine.md`
- Reason: this slice changes progress accounting only. It does not add, remove or rename business, UI, read model, worker, operation barrier, force-refresh, permission or legacy-retirement states.

## Seven Test Categories

This is an audit/accounting slice. No new runtime code is changed.

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | already covered | `tests/test_batch_accounting_api.py` covers amount rules, version conflicts, relation ownership, repair behavior. |
| 2. Service-layer tests | already covered | `BatchAccountingService` command-boundary and repair tests. |
| 3. API contract tests | already covered | GET/submit/withdraw status/error/freshness tests. |
| 4. Read model/cache/background job tests | already covered locally, production evidence deferred | relation facade/projection/worker registry/App Status tests documented; real worker drain deferred. |
| 5. Frontend component and interaction tests | already covered | `BatchAccountingPage.test.tsx`, operation barrier tests and E2E docs. |
| 6. End-to-end business-flow integration tests | local/browser covered, production evidence deferred | Playwright flow documented; real production data flow deferred. |
| 7. Existing feature regression tests | already covered | static route guards and batch accounting API regressions. |

## Verification

Because this is docs/state accounting only, final verification is:

- `bash scripts/verify.sh docs`
- `git diff --check`

