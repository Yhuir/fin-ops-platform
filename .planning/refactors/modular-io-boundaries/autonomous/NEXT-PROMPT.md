# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `no_oa_bank_batch` is the eleventh non-Go read model implementation pilot.
- `NoOaBankBatchReadModelPersistencePort` now owns no-OA public snapshot persistence delegation for the worker refresh path.
- `NoOaBankBatchReadModelRefreshService.handle_runtime_event(...)` no longer directly calls broad `state_store.save_no_oa_bank_batches(...)`.
- SQL cleanup/write ownership remains in `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)`.
- The no-OA list/query path still consumes broad `workbench_sql_read_repository.list_no_oa_bank_batch_rows(...)` from `NoOaBankBatchApplicationService`.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:no-oa-bank-batch-read-model-repository-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-refresh-persistence-boundary-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-repository-state-store-boundary-audit.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
   - `tests/test_no_oa_bank_batch_application_service.py`
   - `tests/test_read_model_manifest.py`
6. Use CodeGraph for structural lookup and impact before editing.

## Boundary Scope

Target:

- Add a narrow `NoOaBankBatchReadModelRepositoryPort` or local-pattern equivalent for manifest-listed `list_no_oa_bank_batch_rows(...)`.
- Wire `NoOaBankBatchApplicationService` list/query construction through the narrow no-OA repository port instead of broad `workbench_sql_read_repository`.
- Preserve list payload shape, missing/stale/fresh/unavailable status behavior, refresh enqueue behavior, pagination behavior and public lifecycle filtering.
- Preserve `PostgresReadModelRepository.list_no_oa_bank_batch_rows(...)` as SQL owner; do not duplicate SQL.
- Add a port guard proving unrelated read model methods are not exposed.
- Update manifest `repository_owner` only if the port becomes the new owner name.
- Update state/docs/tests accounting.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not change business rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_workbench_integration -v`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified no-OA read model repository port extraction slice, commit and push to `origin/dev`, then continue to the next selected boundary unless a hard stop gate is hit.
