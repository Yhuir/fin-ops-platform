# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:workbench-relation-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:workbench-relation-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_detail` current local implementation support slices are complete through the collaborator audit, but this is not full module closure.
- `workbench_relation` is selected as the next read model implementation pilot.
- `WorkbenchRelationReadModelRepositoryPort` is now wired into app/worker/projection builder relation read-model paths.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`read-models:workbench-relation-derived-lifecycle-executor-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-workbench-relation-repository-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
5. Use CodeGraph for structural lookup of `Application._derived_lifecycle_workbench_relation_read_model_executor`, `_enqueue_generic_read_model_refreshes`, `BankDetailDerivedLifecycleExecutor`, and callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Extract the app-level `Application._derived_lifecycle_workbench_relation_read_model_executor(...)` behavior into an explicit service/port.
- Preserve current scope selection:
  - explicit domain-plan scope keys win;
  - fallback remains `["all"]`.
- Preserve enqueue through `ReadModelRefreshGateway` / `_enqueue_generic_read_model_refreshes` equivalent behavior.
- Preserve response payload shape:
  - `deleted_counts`
  - `invalidated_scopes`
  - `enqueued_jobs`
- Keep `server.py` as dependency wiring / executor registry only.
- Add focused tests for explicit scope, all fallback, metadata/reason forwarding and payload shape.

Forbidden:

- Do not migrate canonical relation write lifecycle in this slice.
- Do not change `workbench_relation` read model refresh service behavior.
- Do not migrate pending invoice, OA pending, invoice usage/collection, no-OA, turnover, batch accounting, cost/tax/search in the same slice.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- Runtime code changes scoped to the derived lifecycle executor boundary.
- Focused tests for the new service/port.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `read-models:workbench-relation-derived-lifecycle-executor-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
