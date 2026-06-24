# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:search-refresh-producer-invalidation-service-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:search-refresh-producer-invalidation-service-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `search` is the twelfth non-Go read model pilot.
- `SearchReadModelRepositoryPort` owns manifest-listed `search_index(...)` and `save_search_index_rows(...)`.
- Search rebuild ownership stays in `SearchPendingSqlProjectionBuilder`; app-owned rebuild helpers were removed.
- `SearchQueryFreshnessService` owns `/api/search` SQL miss/stale/source-version payload assembly.
- `SearchIndexSourceVersionsProvider` owns search expected source-version proof.
- `SearchReadModelRefreshProducer` owns search refresh enqueue and invalidation scope normalization.
- App-owned search query freshness and refresh producer helpers were removed and guarded from returning.
- `search` remains `implementation-gap-open` pending local closure audit and real environment evidence accounting.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:search-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-query-freshness-service-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-refresh-producer-invalidation-boundary-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-refresh-producer-invalidation-service-extraction.md`
   - `docs/modules/search/README.md`
   - `docs/modules/search/state-machine.md`
   - `docs/modules/search/tests.md`
   - `docs/modules/search/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/search_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/search_query_freshness_service.py`
   - `backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py`
   - `tests/test_search_pending_sql_runtime.py`
   - `tests/test_search_api.py`
   - `tests/test_runtime_worker_registry.py`
6. Use CodeGraph for remaining search-related `Application` methods/callers before claiming local closure.

## Boundary Scope

Target:

- Audit search after repository port, rebuild helper quarantine, query freshness service extraction and refresh producer extraction.
- Determine whether local implementation support can move to `production-evidence-deferred`, or whether another local implementation gap must be split first.
- Check `Application`, worker, projection, repository port, manifest, runtime worker registry, App Status, tests and docs for remaining search boundary contamination.
- Do not mark `search` globally closed unless real PostgreSQL/worker/App Status/high-row/browser evidence is available and verified.

Forbidden:

- Do not change search ranking, API response shape, permission behavior, worker event names, scope policy, queue schema, Redis/cache behavior or frontend behavior unless a verified gap requires it and tests are updated.
- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed without full closure evidence.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Relevant platform boundary guard tests.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified search local implementation closure audit or the first split implementation gap, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
