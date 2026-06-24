# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:no-oa-bank-batch-repository-state-store-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:no-oa-bank-batch-repository-state-store-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `no_oa_bank_batch` is the eleventh non-Go read model implementation pilot.
- The audit found the current no-OA registration contracts are explicit: manifest, scope policy, runtime worker registry and route mapping are present.
- SQL cleanup/write ownership for public no-OA snapshot persistence currently lives in `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)`.
- `PostgresStateStore.save_no_oa_bank_batches(...)` remains a broad façade over that SQL owner plus fallback snapshot persistence.
- `NoOaBankBatchReadModelRefreshService` still directly calls broad `state_store.save_no_oa_bank_batches(snapshot)` after `NoOaBankBatchService.public_snapshot()`.
- The first implementation target is refresh persistence boundary extraction, not list-only repository port extraction.
- `NoOaBankBatchReadModelRepositoryPort` for `list_no_oa_bank_batch_rows` remains a later read-side boundary.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-repository-state-store-boundary-audit.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
   - `backend/src/fin_ops_platform/services/postgres_state_store.py`
   - `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
   - `tests/test_no_oa_bank_batch_read_model_refresh.py`
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph for structural lookup and impact before editing.

## Boundary Scope

Target:

- Introduce a narrow no-OA read model refresh persistence boundary/adapter around the existing `save_no_oa_bank_batches(...)` capability.
- Wire `NoOaBankBatchReadModelRefreshService` to use that explicit boundary instead of directly calling broad `state_store.save_no_oa_bank_batches(...)` from `handle_runtime_event(...)`.
- Preserve existing SQL ownership in `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)`; do not duplicate SQL.
- Preserve local/Mongo compatibility by delegating through the existing store capability.
- Keep `NoOaBankBatchService.public_snapshot()` as the public lifecycle projection source.
- Preserve stale source-version skip, month-scope refresh behavior, relation-repair prohibition, queue completion, event type, scope type and return payload.
- Add or update service-layer/read model/background job regression tests and static boundary guard coverage.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not extract the list-only `NoOaBankBatchReadModelRepositoryPort` in this slice unless the persistence boundary proves impossible without it.
- Do not change business rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_workbench_integration tests.test_platform_runtime_boundary_guards -v`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified no-OA refresh persistence boundary implementation slice, commit and push to `origin/dev`, then continue to the next selected boundary unless a hard stop gate is hit.
