# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:no-oa-pair-service-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:no-oa-pair-service-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- No-OA normal relation writes are command-service gated.
- No-OA active relation reads mostly use `relation_facade`.
- No-OA application snapshot/persist/rollback pair service usage still needs extraction.
- No-OA domain repair/read pair service usage remains for later classification.
- ETC and WorkbenchWriteFacade relation dependencies still need focused classification.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:no-oa-application-pair-snapshot-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-pair-service-boundary-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - relevant no-OA relation tests.
5. Use CodeGraph/text search for `NoOaBankBatchApplicationService`, `pair_relation_service`, `_pair_relation_service`, `snapshot_case_ids`, `save_no_oa_bank_batch_mutation`, `save_workbench_pair_relations`, `_restore_snapshots`, and `pair_relation_snapshot_by_case_id`.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Extract no-OA application pair snapshot/version/persist/rollback usage into an explicit collaborator or port.
- Preserve existing `save_no_oa_bank_batch_mutation(...)` and fallback persistence payload shapes.
- Preserve rollback behavior for submit/submit-selection/internal-transfer/withdraw persistence failures.
- Keep normal relation writes on `WorkbenchRelationCommandService`.
- Keep active relation reads on `WorkbenchRelationReadFacade`.
- Do not migrate `NoOaBankBatchService._repair_submitted_no_oa_relation_consistency(...)` or `_has_active_no_oa_relation(...)` in this slice.
- Produce an implementation analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not change no-OA submit/withdraw/internal transfer business rules, API payloads, dirty scope semantics, read model refresh semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:no-oa-application-pair-snapshot-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
