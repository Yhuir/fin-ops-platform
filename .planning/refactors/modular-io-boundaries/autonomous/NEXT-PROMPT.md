# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:no-oa-bank-batch-read-model-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:no-oa-bank-batch-read-model-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `no_oa_bank_batch` is the eleventh non-Go read model implementation pilot.
- `NoOaBankBatchReadModelPersistencePort` owns no-OA public snapshot persistence delegation for the worker refresh path.
- `NoOaBankBatchReadModelRefreshService.handle_runtime_event(...)` no longer directly calls broad `state_store.save_no_oa_bank_batches(...)`.
- `NoOaBankBatchReadModelRepositoryPort` owns no-OA list/query read model repository access.
- `PostgresStateStore.no_oa_bank_batch_sql_read_repository` exposes the no-OA port over the SQL read model repository.
- `NoOaBankBatchApplicationService.list_batches_payload(...)` no longer reads through broad `workbench_sql_read_repository`.
- `READ_MODEL_MANIFEST["no_oa_bank_batch"].repository_owner` is `NoOaBankBatchReadModelRepositoryPort`.
- No module is globally closed.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-read-model-repository-port-extraction.md`
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
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
   - `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
   - relevant no-OA tests.
6. Use CodeGraph for structural lookup and impact before editing.

## Boundary Scope

Target:

- Audit no-OA refresh enqueue, derived lifecycle, force refresh, operation barrier, dirty/outbox, App Status, worker registry and remaining app-owned helper surfaces after repository/persistence port extraction.
- Confirm non-transactional refresh enqueue goes through `ReadModelRefreshGateway` and scope policy registry.
- Confirm transactional/mutation paths expose affected scopes/months and preserve operation barrier semantics.
- Confirm no page can display stale no-OA read model payload as fresh.
- Classify old route/service/repository/read model/frontend API/worker paths as removed, quarantined, compat-only or blocked-by-human-gate.
- If a concrete local implementation gap is found, split the first narrow implementation boundary and execute it.
- If no local implementation gap remains, perform no-OA local implementation closure accounting and defer only real PostgreSQL/worker/App Status/high-row/browser evidence.
- Update state/docs/tests accounting.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not change business rules, API shapes, worker event names, queue schema, Redis/cache behavior, permissions, audit meaning or frontend behavior unless a verified gap requires it and tests are updated.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_workbench_integration tests.test_read_model_manifest -v`
- Targeted platform/runtime guard tests for any guard touched.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified no-OA freshness/derived lifecycle audit or first split implementation slice, commit and push to `origin/dev`, then continue to the next selected boundary unless a hard stop gate is hit.
