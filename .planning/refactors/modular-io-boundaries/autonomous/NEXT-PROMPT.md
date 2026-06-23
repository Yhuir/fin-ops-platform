# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:workbench-write-facade-relation-read-snapshot-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:workbench-write-facade-relation-read-snapshot-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- WorkbenchWriteFacade active relation reads, withdraw preview fallback and pair snapshots now go through `WorkbenchWriteRelationReadSnapshotPort`.
- Core confirm/cancel/withdraw writes remain command-service gated by existing guards.
- Cash special metadata mutation still uses direct pair service mutation methods and remains the next boundary to audit.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:workbench-write-facade-cash-special-metadata-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-relation-read-snapshot-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-workbench-write-facade-pair-service-boundary-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
   - `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
   - `tests/test_workbench_write_characterization.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `update_special_metadata_for_row_ids`, `clear_special_metadata_for_row_ids`, `_active_relation_for_cash_special`, `confirm_cash_pass_through`, `confirm_cash_ticket_purchase`, `cancel_cash_special`, `relation_command_service`, `WorkbenchRelationCommandService`, and `WorkbenchWriteFacade`.
6. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit remaining WorkbenchWriteFacade cash special metadata direct pair service mutations.
- Classify whether they should be moved behind an explicit command-service capability, a narrow special-metadata mutation port, or a compat-only quarantine.
- Record owner, caller list, rollback/idempotency implications, forbidden writes, tests required, and deletion/migration condition.
- Select the next smallest safe implementation boundary.
- Do not implement the mutation migration unless the audit proves the implementation is small, self-contained, and covered by existing tests in the same slice.

Forbidden:

- Do not remove `pair_relation_service` from WorkbenchWriteFacade until cash special metadata mutation has a replacement boundary.
- Do not change relation write semantics, cash special status semantics, API payloads, dirty scope semantics, read model refresh semantics or Workbench active generation behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Analysis/accounting slice for cash special metadata boundary.
- Updated docs/state/queue/journal/next prompt.
- Targeted Workbench write characterization/static guard/docs verification and `git diff --check` as applicable.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:workbench-write-facade-cash-special-metadata-boundary-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
