# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:search-oa-projection-sync-refresh-producer-boundary-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:search-oa-projection-sync-refresh-producer-boundary-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `search` is the twelfth non-Go read model pilot.
- `SearchReadModelRepositoryPort` owns manifest-listed `search_index(...)` and `save_search_index_rows(...)`.
- Search rebuild ownership stays in `SearchPendingSqlProjectionBuilder`.
- `SearchQueryFreshnessService` owns `/api/search` SQL miss/stale/source-version payload assembly.
- `SearchIndexSourceVersionsProvider` owns search expected source-version proof.
- `SearchReadModelRefreshProducer` owns search refresh enqueue and invalidation scope normalization.
- Production PostgreSQL `/api/search` without a SQL repository fails closed instead of live scanning legacy/local state.
- `OAProjectionSyncService` now routes Search downstream dirty fan-out through `SearchReadModelRefreshProducer` instead of direct `enqueue_many("search", ...)`.
- `search` remains `implementation-gap-open` pending post-OA-sync local closure audit and real environment evidence accounting.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:search-post-oa-projection-sync-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-post-fail-closed-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-oa-projection-sync-refresh-producer-boundary-extraction.md`
   - `docs/modules/search/README.md`
   - `docs/modules/search/state-machine.md`
   - `docs/modules/search/tests.md`
   - `docs/modules/search/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/worker.py`
   - `backend/src/fin_ops_platform/services/search_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/search_query_freshness_service.py`
   - `backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/oa_projection_sync.py`
   - `tests/test_search_pending_sql_runtime.py`
   - `tests/test_search_api.py`
   - `tests/test_runtime_worker_registry.py`
   - `tests/test_oa_projection_sync_service.py`
   - `tests/test_oa_projection_sql_runtime.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Re-audit search after OA projection sync producer extraction.
- Decide whether local implementation support can move to `production-evidence-deferred`, or whether another local implementation gap must be split first.
- Do not mark `search` globally closed unless real PostgreSQL/worker/App Status/high-row/browser evidence is available and verified.

Expected verification:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified search post-OA-sync local implementation closure audit or the first split implementation gap, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
