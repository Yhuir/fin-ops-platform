# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:workbench-relation-derived-lifecycle-executor-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:workbench-relation-derived-lifecycle-executor-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_detail` current local implementation support slices are complete through the collaborator audit, but this is not full module closure.
- `workbench_relation` is the current read model implementation pilot.
- `WorkbenchRelationReadModelRepositoryPort` is wired into app/worker/projection builder relation read-model paths.
- `WorkbenchRelationDerivedLifecycleExecutor` owns the derived lifecycle refresh enqueue payload behavior.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`read-models:workbench-relation-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-workbench-relation-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-workbench-relation-derived-lifecycle-executor-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_read_facade.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_sql_projection.py`
5. Use CodeGraph for structural lookup of current `workbench_relation` app/server helpers, relation command service construction, read facade usage, projection builder ownership, repository SQL ownership and lifecycle executor registry.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit remaining local `workbench_relation` implementation gaps after repository port extraction and derived lifecycle executor extraction.
- Decide the next narrow boundary from evidence, not from Go hot-path preference.
- Classify each remaining gap as:
  - already-closed local evidence;
  - implementation-pending;
  - compat-only/quarantined;
  - production-evidence-deferred;
  - blocked-by-human-gate.
- At minimum evaluate:
  - relation write lifecycle still owned by `WorkbenchRelationCommandService` / `server.py` / repositories;
  - `PostgresWorkbenchRepository` versus relation-specific SQL owner split;
  - `WorkbenchRelationReadFacade` freshness/force-refresh/operation-barrier evidence;
  - `workbench_relation` refresh service and worker queue evidence;
  - service factory collaborator wiring that is only dependency assembly versus business logic;
  - legacy direct pair mutation paths and static guards;
  - production evidence that must remain deferred without staging or local `PGSQL_URL`.
- Produce an analysis file with explicit next-boundary selection.

Forbidden:

- Do not implement relation write lifecycle migration during this audit slice.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.
- Do not mark `workbench_relation` full module closed unless every local closure requirement and environment evidence/defer rule is satisfied.

## Expected Output

- One analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- If a narrow next implementation boundary is selected, insert it before Go candidates.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the queued implementation boundary if safe.

## Stop Condition

Complete one verified `read-models:workbench-relation-local-implementation-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
