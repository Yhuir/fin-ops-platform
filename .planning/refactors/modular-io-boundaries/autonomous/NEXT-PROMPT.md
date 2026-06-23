# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:no-oa-application-pair-snapshot-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:no-oa-application-pair-snapshot-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- No-OA application snapshot/version/persist/rollback pair service usage now goes through `NoOaPairRelationSnapshotPort`.
- No-OA normal relation writes remain command-service gated.
- No-OA active relation reads remain facade-backed.
- No-OA domain repair/read pair service usage remains in `NoOaBankBatchService`.
- ETC and WorkbenchWriteFacade relation dependencies still need focused classification.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:no-oa-domain-repair-read-port-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-pair-service-boundary-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-application-pair-snapshot-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `tests/test_no_oa_bank_batch_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `NoOaBankBatchService`, `_pair_relation_service`, `_repair_submitted_no_oa_relation_consistency`, `_has_active_no_oa_relation`, `_build_batches_for_month_scope`, `active_relations_for_row_ids`, `get_active_relation_by_case_id`, `relation_facade`, and `relation_command_service`.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit `NoOaBankBatchService` pair relation service usage in domain repair and relation-backed stale/submitted projection.
- Classify each usage as removable, compat-only, or requiring a read/repair port.
- Determine whether the next boundary should be an implementation extraction, a guard-only slice, or another smaller audit.
- Preserve the existing command-service write path for no-OA relation repair.
- Preserve relation-backed stale projection behavior until a tested replacement exists.
- Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not migrate `NoOaBankBatchApplicationService`; it was handled in the previous slice.
- Do not change no-OA submit/withdraw/internal transfer business rules, API payloads, dirty scope semantics, read model refresh semantics or production state.
- Do not remove domain repair/read behavior without tests proving equivalent behavior.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:no-oa-domain-repair-read-port-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
