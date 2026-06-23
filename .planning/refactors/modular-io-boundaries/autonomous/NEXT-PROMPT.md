# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:workbench-matching-relation-read-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:workbench-matching-relation-read-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Workbench matching/orchestrator active relation reads now go through `WorkbenchMatchingRelationReadPort`.
- Matching read port is backed by existing `WorkbenchRelationCommandService` read methods in `Application` wiring.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:server-relation-read-helper-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-matching-relation-read-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect remaining direct relation read helpers in:
   - `backend/src/fin_ops_platform/app/server.py`
   - existing route/service owners called by those helpers
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph/text search for `_workbench_pair_relation_service`, `list_active_relations`, `active_relations_for_row_ids`, `get_active_relation_by_row_id`, and `snapshot`.
7. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit every remaining `server.py` direct `_workbench_pair_relation_service` read helper/call site.
- Classify each touched old path as removed, explicit-port candidate, compat-only, or blocked-by-human-gate.
- Identify the next smallest safe extraction/removal boundary.
- Keep this slice analysis-only unless the audit proves a trivial unused helper can be safely removed without widening scope.

Forbidden:

- Do not change relation writes, matching rules, read model refresh, dirty scopes, API response shape or frontend behavior in the audit slice.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.
- Do not convert canonical relation reads to downstream read model payloads unless the audit proves it is semantically correct.

## Expected Output

- Analysis/accounting slice for remaining `server.py` relation read helpers.
- Updated state/queue/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:server-relation-read-helper-boundary-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
