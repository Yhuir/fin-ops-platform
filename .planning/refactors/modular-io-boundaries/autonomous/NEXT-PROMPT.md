# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:workbench-relation-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:workbench-relation-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction and derived lifecycle executor extraction are locally complete.
- The audit selected transaction persist repository owner split as the next narrow implementation boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:transaction-persist-repository-owner-split`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-workbench-relation-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph for `_persist_workbench_pair_relations_in_transaction`, `PostgresWorkbenchRelationRepository.save_workbench_pair_relations`, `PostgresWorkbenchRepository.save_workbench_pair_relations`, and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Replace `Application._persist_workbench_pair_relations_in_transaction(...)` broad repository usage:
  - from `PostgresWorkbenchRepository(transaction).save_workbench_pair_relations(...)`
  - to `PostgresWorkbenchRelationRepository(transaction).save_workbench_pair_relations(...)`
- Preserve snapshot selection, `changed_case_ids` normalization, transaction requirement and cache clearing behavior.
- Add or update a focused static guard proving transaction pair relation persist uses `PostgresWorkbenchRelationRepository` and not broad `PostgresWorkbenchRepository`.
- Run targeted relation repository/guard tests.

Forbidden:

- Do not migrate relation command service lifecycle in this slice.
- Do not remove app-level command repository snapshot/apply helpers in this slice.
- Do not change relation business rules, API payloads, write semantics, dirty scope semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Runtime code change scoped to the transaction persist repository owner.
- Focused guard/test update.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted verification, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:transaction-persist-repository-owner-split` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
