# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:transaction-persist-closure-accounting-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:transaction-persist-closure-accounting-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Transaction and non-transaction persist surfaces are locally accounted for.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:rollback-closure-accounting-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-transaction-persist-closure-accounting-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-pair-relation-rollback-restore-service-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-exception-rollback-restore-service-extraction.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
   - `backend/src/fin_ops_platform/services/workbench_exception_rollback_restore_service.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `_restore_workbench_pair_relation_snapshot`, `_restore_workbench_exception_pair_snapshots`, `WorkbenchPairRelationRollbackRestoreService`, `WorkbenchExceptionRollbackRestoreService`, `restore_pair_relation_snapshot`, and rollback restore tests.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit pair relation and exception rollback restore surfaces.
- Classify each as implemented, compat-only, next implementation boundary, production-evidence-deferred, or blocked-by-human-gate.
- Decide whether rollback restore is locally accounted for or whether a narrow implementation slice is still required.
- Do not mark the module closed unless local evidence proves all implementation gaps are closed.

Forbidden:

- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior during the audit.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Analysis/accounting slice.
- Updated queue/state/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:rollback-closure-accounting-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
