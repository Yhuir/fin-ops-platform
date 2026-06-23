# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:workbench-write-facade-pair-service-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:workbench-write-facade-pair-service-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- WorkbenchWriteFacade pair service call sites are classified.
- Core confirm/cancel writes are already command-service gated by existing guards.
- Cash special metadata mutation still uses direct pair service and remains a later boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:workbench-write-facade-relation-read-snapshot-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-pair-service-boundary-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_write_characterization.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `_pair_relation_service`, `active_relations_for_row_ids`, `get_active_relation_by_row_id`, `snapshot`, `preview_withdraw_for_row_ids`, `relation_command_service`, `restore_pair_relation_snapshot`, and `WorkbenchWriteFacade`.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add an explicit WorkbenchWriteFacade relation read/snapshot port.
- Move these pair service methods behind the port:
  - `active_relations_for_row_ids(...)`
  - `get_active_relation_by_row_id(...)`
  - `preview_withdraw_for_row_ids(...)`
  - `snapshot()`
- Inject the port into `WorkbenchWriteFacade` from `Application._workbench_write_facade(...)`.
- Preserve command-service-backed writes.
- Preserve confirm/cancel/withdraw/idempotency/UoW behavior.
- Strengthen static guards so WorkbenchWriteFacade no longer directly calls pair service read/snapshot methods outside the new port.
- Produce an implementation analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not migrate cash special metadata mutation methods in this slice.
- Do not remove `pair_relation_service` from WorkbenchWriteFacade entirely if special metadata mutation still needs it.
- Do not change relation write semantics, API payloads, dirty scope semantics, read model refresh semantics or Workbench active generation behavior.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Implementation/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted Workbench write characterization tests, boundary guards, app check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:workbench-write-facade-relation-read-snapshot-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
