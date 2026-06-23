# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:no-oa-domain-repair-read-port-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:no-oa-domain-repair-read-port-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- No-OA application snapshot/version/persist/rollback pair service usage goes through `NoOaPairRelationSnapshotPort`.
- No-OA normal relation writes remain command-service gated.
- No-OA active relation reads in application service remain facade-backed.
- No-OA domain repair/read pair service usage in `NoOaBankBatchService` has been audited and should be extracted next.
- ETC and WorkbenchWriteFacade relation dependencies still need focused classification.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:no-oa-domain-repair-read-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-domain-repair-read-port-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-application-pair-snapshot-port-extraction.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
   - `tests/test_no_oa_bank_batch_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `NoOaBankBatchService`, `_pair_relation_service`, `_repair_submitted_no_oa_relation_consistency`, `_has_active_no_oa_relation`, `_build_batches_for_month_scope`, `active_relations_for_row_ids`, `get_active_relation_by_case_id`, `_confirm_no_oa_relation`, and `_cancel_no_oa_relation`.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Introduce an explicit no-OA relation read/repair port for `NoOaBankBatchService`.
- Move active relation by case id and active relations for row ids reads behind the port.
- Inject the port into `NoOaBankBatchService` and `from_snapshot(...)`.
- Forward the same port into month-scoped child services.
- Preserve command-service-backed `_confirm_no_oa_relation(...)` and `_cancel_no_oa_relation(...)` writes.
- Preserve relation-backed stale-as-submitted public projection and withdraw eligibility.
- Preserve submitted relation repair behavior and stale no-OA relation cancellation behavior.
- Strengthen `tests/test_platform_runtime_boundary_guards.py` so `NoOaBankBatchService` no longer stores or calls `_pair_relation_service` directly after extraction.
- Produce an implementation analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not change no-OA batch status semantics.
- Do not change submit, withdraw, internal transfer, dirty scope, read model refresh or API payloads.
- Do not remove repair/read behavior without equivalent tests.
- Do not migrate application snapshot/persist/rollback again.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Implementation/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted no-OA service tests, boundary guards, app check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:no-oa-domain-repair-read-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
