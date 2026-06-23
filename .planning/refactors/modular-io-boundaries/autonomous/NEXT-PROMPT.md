# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:rollback-closure-accounting-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:rollback-closure-accounting-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Transaction/non-transaction persist and rollback restore surfaces are locally accounted for.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:whole-state-persistence-closure-accounting-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-rollback-closure-accounting-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-transaction-persist-closure-accounting-audit.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/services/state_store.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `_persist_state`, `workbench_pair_relations`, `save_workbench_pair_relations`, `load_workbench_pair_relations`, `WorkbenchPairRelationService.from_snapshot`, and state store relation tests.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit whole-state persistence, bootstrap and compatibility snapshot paths.
- Classify each as implemented, compat-only, next implementation boundary, production-evidence-deferred, or blocked-by-human-gate.
- Decide whether remaining full-state paths are acceptable compatibility surfaces, need quarantine, or need a narrow implementation slice before local closure/defer.
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

Complete one verified `workbench-relations:whole-state-persistence-closure-accounting-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
