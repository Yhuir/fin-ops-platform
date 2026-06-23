# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:whole-state-persistence-closure-accounting-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:whole-state-persistence-closure-accounting-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Broad `_persist_state(...)` still serializes relation snapshot facts and is the next implementation gap.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:persist-state-relation-snapshot-quarantine`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-whole-state-persistence-closure-accounting-audit.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/services/state_store.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - `tests/test_app_postgres_mode.py`
   - `tests/test_state_store_contract.py`
   - `tests/test_postgres_state_store.py`
5. Use CodeGraph/text search for `_persist_state`, `_persist_state_with_workbench_invalidation`, `workbench_pair_relations`, `save_workbench_pair_relations`, `load_workbench_pair_relations`, and state store relation tests.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Remove or quarantine relation snapshot facts from broad `Application._persist_state(...)`.
- Preserve relation-specific persistence through `_persist_workbench_pair_relations(...)`, `_schedule_workbench_pair_relation_persist(...)`, `_persist_workbench_pair_relations_in_transaction(...)`, command repository save paths and state-store domain methods.
- Preserve app bootstrap loading through `load_workbench_pair_relations`.
- Preserve local/Mongo relation domain save/load contract.
- Add or update a static/runtime guard proving broad `_persist_state(...)` no longer serializes relation snapshot facts.
- Do not mark the module closed unless local evidence proves all implementation gaps are closed.

Forbidden:

- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior beyond the narrow full-state quarantine.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated queue/state/journal/next prompt.
- Targeted tests, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:persist-state-relation-snapshot-quarantine` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
