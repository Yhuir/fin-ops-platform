# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:server-auto-pair-conflict-relation-read-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:server-auto-pair-conflict-relation-read-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Server repair/precondition read ports for OA invoice offset, OA attachment repair, confirm-link context and auto-pair conflict are now extracted.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:post-server-precondition-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-auto-pair-conflict-relation-read-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-relation-read-helper-boundary-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect current remaining references to `_workbench_pair_relation_service`, `WorkbenchPairRelationService`, relation snapshot, relation persist, case id allocation, rollback, whole-state persistence, command-service surfaces and relation read model helpers.
6. Use CodeGraph/text search for remaining direct relation service dependencies and classify each as implemented, compat-only, next implementation boundary, production-evidence-deferred, or blocked-by-human-gate.
7. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Re-audit local `workbench_relation` implementation gaps after server repair/precondition read ports.
- Decide whether the next safe boundary is a concrete implementation slice, a closure/defer accounting slice, or a production evidence defer.
- Do not mark the module closed unless local evidence proves every implementation gap is closed and production evidence requirements are explicitly handled.
- Keep Go hot-path candidates blocked unless all admission prerequisites are satisfied.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed from weak or indirect evidence.
- Do not perform production writes or require local `PGSQL_URL`/staging DB.

## Expected Output

- Analysis/accounting slice only unless a planning inconsistency requires immediate correction.
- Updated queue/state/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:post-server-precondition-local-implementation-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
