# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:post-restore-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:post-restore-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction, transaction persist repository owner split, command repository snapshot adapter extraction, non-transactional pair relation persist service extraction, pair relation rollback restore service extraction and exception rollback restore service extraction are locally complete.
- Local closure audit found remaining implementation gaps; Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:batch-accounting-pair-restore-helper-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-restore-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_batch_accounting.py`
5. Use CodeGraph/text search for `_restore_batch_accounting_pair_relation_snapshot`, `BatchAccountingApiRoutes`, pair relation snapshot/restore wiring and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit BatchAccountingApiRoutes pair relation snapshot/restore wiring.
- Decide whether `_restore_batch_accounting_pair_relation_snapshot(...)` should delegate to `WorkbenchPairRelationRollbackRestoreService`, be removed, or be classified as route-local compat-only.
- Produce an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not migrate batch-accounting restore behavior in this audit slice unless the queue is explicitly split/advanced after analysis.
- Do not change batch-accounting business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice only unless the audit proves a trivial no-code removal.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:batch-accounting-pair-restore-helper-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
