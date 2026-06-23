# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:workbench-write-facade-post-port-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:workbench-write-facade-post-port-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- WorkbenchWriteFacade relation reads/snapshots and cash special metadata mutations go through explicit ports.
- WorkbenchWriteFacade no longer stores broad `_pair_relation_service`.
- WorkbenchWriteFacade constructor still accepts `pair_relation_service` only for default port construction.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:workbench-write-facade-required-port-constructor`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-post-port-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-cash-special-metadata-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_auth_context_idempotency.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `WorkbenchWriteFacade(`, `pair_relation_service=`, `relation_read_snapshot_port=`, `relation_special_metadata_mutation_port=`, and `_pair_relation_service`.
6. Produce or update an implementation/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Remove `pair_relation_service` from `WorkbenchWriteFacade.__init__`.
- Require explicit `relation_read_snapshot_port` and `relation_special_metadata_mutation_port`.
- Keep `WorkbenchWriteRelationReadSnapshotPort` and `WorkbenchWriteRelationSpecialMetadataMutationPort` as the only adapters that hold pair relation service.
- Update `Application._workbench_write_facade(...)` and `tests/test_workbench_auth_context_idempotency.py::_new_facade(...)`.
- Strengthen static guard so WorkbenchWriteFacade cannot re-accept `pair_relation_service`.

Forbidden:

- Do not change relation behavior, cash special behavior, dirty scope semantics, read model refresh semantics or API response shape.
- Do not rewrite the ports into command service native commands in this slice.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Implementation/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted Workbench auth-context/static guard tests, app check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:workbench-write-facade-required-port-constructor` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
