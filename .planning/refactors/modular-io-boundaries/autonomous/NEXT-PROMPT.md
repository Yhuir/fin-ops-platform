# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:search-query-freshness-service-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:search-query-freshness-service-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `search` is the twelfth non-Go read model pilot.
- `SearchReadModelRepositoryPort` owns manifest-listed `search_index(...)` and `save_search_index_rows(...)`.
- `Application.rebuild_search_index_scope(...)` and `_build_search_index_rows_for_month(...)` were removed; rebuild ownership stays in `SearchPendingSqlProjectionBuilder`.
- `SearchQueryFreshnessService` owns `/api/search` SQL miss/stale/source-version payload assembly.
- `SearchIndexSourceVersionsProvider` owns search expected source-version proof.
- `Application._get_search_payload_from_sql_read_model(...)` and `_search_index_expected_source_versions(...)` were removed and guarded from returning.
- `search` remains `implementation-gap-open` because refresh producer and invalidation helpers still live in `Application`.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:search-refresh-producer-invalidation-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-query-freshness-service-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-freshness-helper-boundary-audit.md`
   - `docs/modules/search/README.md`
   - `docs/modules/search/state-machine.md`
   - `docs/modules/search/tests.md`
   - `docs/modules/search/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/search_query_freshness_service.py`
   - `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
   - `tests/test_search_pending_sql_runtime.py`
   - `tests/test_search_api.py`
   - `tests/test_write_operation_slo_audit.py`
6. Use CodeGraph for `_enqueue_search_read_model_refresh`, `_invalidate_search_read_model_scopes`, settings update search invalidation, import-state search invalidation and workbench-scope invalidation callers.

## Boundary Scope

Target:

- Audit app-owned search refresh producer and invalidation helper ownership.
- Classify `_enqueue_search_read_model_refresh(...)` as removable, extractable producer, or temporary dependency-assembly wrapper.
- Classify `_invalidate_search_read_model_scopes(...)` as removable, extractable invalidation service/producer, or compat-only wrapper.
- Confirm all touched refresh enqueue paths still go through `ReadModelRefreshGateway` and search scope policy.
- Split a smaller implementation boundary if the audit finds multiple independent gaps.

Forbidden:

- Do not change search ranking, API response shape, permission behavior, worker event names, scope policy, queue schema, Redis/cache behavior or frontend behavior unless a verified gap requires it and tests are updated.
- Do not implement Go/Fiber/Go Worker.
- Do not mark `search` or any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Relevant platform boundary guard tests.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified search refresh producer/invalidation boundary audit or the first split implementation slice, commit and push to `origin/dev`, then continue to the next safe search boundary unless a hard stop gate is hit.
