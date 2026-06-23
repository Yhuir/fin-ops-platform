# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:workbench-matching-pair-service-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:workbench-matching-pair-service-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Matching/orchestrator broad pair service reads are canonical active relation reads for held-row suppression and auto-completion preconditions.
- `WorkbenchRelationCommandService` already exposes `list_active_relations()` and `active_relations_for_row_ids(...)`.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:workbench-matching-relation-read-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-matching-pair-service-boundary-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect:
   - `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
   - `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_matching_orchestrator.py`
   - `tests/test_workbench_reconciliation_engine.py`
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph/text search for `WorkbenchMatchingOrchestrator`, `WorkbenchReconciliationEngine`, `pair_relation_service`, `_pair_relation_service`, `list_active_relations`, and `active_relations_for_row_ids`.
7. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add an explicit matching relation read port for canonical active relation reads used by `WorkbenchMatchingOrchestrator` and `WorkbenchReconciliationEngine`.
- Move `list_active_relations()` and `active_relations_for_row_ids(...)` usage behind that port.
- Update `Application` wiring to inject the port, preferably backed by existing `WorkbenchRelationCommandService` read methods.
- Keep matching candidate suppression, decision generation, auto-completion, dirty scope, read model invalidation and API behavior unchanged.
- Add or strengthen static guard coverage so matching/orchestrator classes no longer accept or store broad `pair_relation_service`.

Forbidden:

- Do not change matching rules, grouping, candidate generation, auto-completion semantics, dirty scopes, read model refresh, relation writes, API response shape or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted Workbench matching/orchestrator and reconciliation engine tests.
- App check, docs verification, and `git diff --check` as applicable.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:workbench-matching-relation-read-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
