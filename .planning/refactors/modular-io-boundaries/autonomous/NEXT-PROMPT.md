# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:exception-rollback-restore-service-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:exception-rollback-restore-service-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction, transaction persist repository owner split, command repository snapshot adapter extraction, non-transactional pair relation persist service extraction, pair relation rollback restore service extraction and exception rollback restore service extraction are locally complete.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:post-restore-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-exception-rollback-restore-service-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
5. Use CodeGraph and text search to re-audit remaining app-owned workbench relation helpers, restore helpers, callback wiring and relation lifecycle gaps.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Re-audit local `workbench_relation` implementation gaps after repository port, lifecycle executor, transaction owner split, command adapter, persist service and rollback restore extractions.
- Decide whether local support slices can enter production-evidence-deferred, whether another narrow cleanup is required, or whether Go admission must remain blocked by local gaps.
- Produce an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not claim full module closure without production PostgreSQL/worker/App Status/high-row/browser evidence or explicit defer status.
- Do not run Go admission while local implementation gaps remain.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice only unless the audit proves a trivial no-code removal.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:post-restore-local-implementation-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
