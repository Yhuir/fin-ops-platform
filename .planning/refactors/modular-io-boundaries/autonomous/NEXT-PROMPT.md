# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:workbench-write-facade-cash-special-metadata-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:workbench-write-facade-cash-special-metadata-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- WorkbenchWriteFacade active relation reads, withdraw preview fallback and pair snapshots go through `WorkbenchWriteRelationReadSnapshotPort`.
- WorkbenchWriteFacade cash special metadata mutation is audited and should move behind an explicit mutation port next.
- Existing command service metadata merge is not a drop-in replacement for cash special clear/replace behavior.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:workbench-write-facade-cash-special-metadata-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-cash-special-metadata-boundary-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-relation-read-snapshot-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_write_characterization.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `WorkbenchWriteFacade`, `update_special_metadata_for_row_ids`, `clear_special_metadata_for_row_ids`, `confirm_cash_pass_through`, `confirm_cash_ticket_purchase`, `cancel_cash_special`, and `WorkbenchWriteRelationReadSnapshotPort`.
6. Produce or update an implementation/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add `WorkbenchWriteRelationSpecialMetadataMutationPort`.
- Move WorkbenchWriteFacade direct pair service calls to `update_special_metadata_for_row_ids(...)` and `clear_special_metadata_for_row_ids(...)` behind the port.
- Inject the port from `Application._workbench_write_facade(...)`.
- Preserve cash special validation, stale conflict checks, metadata payloads, history operation names, response shape, pair relation persist scheduling and read model scheduling.
- Strengthen static guards so WorkbenchWriteFacade no longer directly calls pair service special metadata mutation methods.

Forbidden:

- Do not change cash special API payloads, messages, merge/clear semantics, relation write semantics, dirty scope semantics, read model refresh semantics or Workbench active generation behavior.
- Do not change the command service in this slice unless a failing test proves it is necessary.
- Do not remove the read/snapshot port.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Implementation/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted Workbench write characterization tests, boundary guards, app check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:workbench-write-facade-cash-special-metadata-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
