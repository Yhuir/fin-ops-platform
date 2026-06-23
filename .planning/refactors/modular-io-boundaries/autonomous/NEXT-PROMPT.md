# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:persist-state-relation-snapshot-quarantine` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:persist-state-relation-snapshot-quarantine`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Broad `_persist_state(...)` no longer serializes relation snapshot facts.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:app-health-route-builder-pair-service-injection-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-persist-state-relation-snapshot-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-server-precondition-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/app_health_alert_service.py`
   - `backend/src/fin_ops_platform/services/app_status_overview_service.py`
   - `backend/src/fin_ops_platform/app/*routes*.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `AppHealthAlertService`, `AppStatusOverviewService`, `_workbench_pair_relation_service`, `pair_relation_service`, route builders and remaining pair-service injections.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit app health and route builder pair-service injections.
- Classify each remaining injection as accepted dependency assembly, compat-only, next implementation boundary, production-evidence-deferred, or blocked-by-human-gate.
- Decide whether a narrow code slice is still needed before final local closure/defer accounting.
- Do not mark the module closed unless local evidence proves all implementation gaps are closed.

Forbidden:

- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior beyond the narrow full-state quarantine.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Analysis/accounting slice.
- Updated queue/state/journal/next prompt.
- Docs verification and `git diff --check`; run code tests only if the audit finds and fixes a testable code inconsistency.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:app-health-route-builder-pair-service-injection-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
