# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:pending-invoice-unused-pair-service-removal` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:pending-invoice-unused-pair-service-removal`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Pending invoice query/application services no longer receive `pair_relation_service` constructor injection.
- Pending invoice relation reads use `relation_facade`.
- Pending invoice relation writes use `relation_command_service`.
- No-OA, ETC and WorkbenchWriteFacade relation dependencies still need focused classification.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:no-oa-pair-service-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-pending-invoice-unused-pair-service-removal.md`
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
5. Use CodeGraph/text search for `NoOaBankBatchService`, `NoOaLegacyRelationMigrationService`, `pair_relation_service`, `_pair_relation_service`, `relation_facade`, `relation_command_service`, `confirm_relation`, `withdraw_relation`, and write/read callers.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit no-OA relation dependencies and classify remaining pair service reads/writes.
- Decide whether each no-OA pair service dependency can be removed, should become read-facade/command-service-only, or must remain `compat-only`.
- Classify normal submit/withdraw, internal transfer, legacy migration/repair/consolidation and read model refresh paths separately.
- Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.

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

Complete one verified `workbench-relations:no-oa-pair-service-boundary-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
