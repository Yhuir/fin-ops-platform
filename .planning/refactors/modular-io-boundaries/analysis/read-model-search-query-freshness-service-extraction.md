# Read Model Search Query Freshness Service Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:search-query-freshness-service-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `/api/search` SQL read model fresh/stale/miss payload assembly and expected source-version proof out of `Application` into an explicit search query/freshness service.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-search-freshness-helper-boundary-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-search-app-rebuild-helper-quarantine.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-search-repository-port-extraction.md`
- `docs/modules/search/README.md`
- `docs/modules/search/state-machine.md`
- `docs/modules/search/tests.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/search_read_model_repository.py`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_search_api.py`
- CodeGraph/rg evidence for `_get_search_payload_from_sql_read_model(...)`, `_search_index_expected_source_versions(...)`, `_enqueue_search_read_model_refresh(...)`, `_invalidate_search_read_model_scopes(...)` and `/api/search`.

## Implementation

- Added `SearchIndexSourceVersionsProvider`.
- Added `SearchQueryFreshnessService`.
- Removed `Application._get_search_payload_from_sql_read_model(...)`.
- Removed `Application._search_index_expected_source_versions(...)`.
- `/api/search` now delegates SQL read model payload assembly to `SearchQueryFreshnessService.get_payload(...)`.
- `Application` still owns HTTP parameter validation, HTTP status mapping and legacy/local fallback when no SQL search repository is configured.
- `Application._enqueue_search_read_model_refresh(...)` remains as gateway-backed dependency assembly because `Application._invalidate_search_read_model_scopes(...)` still uses it; this is the next boundary, not closed by this slice.

## Preserved Behavior

- No change to `/api/search` request parameters, response shape, status codes or fallback behavior.
- SQL miss still returns `read_model_status=refreshing` and enqueues `search:<month>` with `api_miss`.
- Existing fresh SQL payloads still return rows without in-memory live scan.
- Source-version mismatch still preserves existing rows, marks `read_model_status=stale`, attaches stale reasons and enqueues `api_source_versions_stale`.
- No change to search ranking, group context, searchable text, worker event names, scope policy, durable queue schema, Redis/cache, permissions, audit or frontend behavior.

## Remaining Search Gaps

- `_enqueue_search_read_model_refresh(...)` is still an app-level gateway-backed producer helper.
- `_invalidate_search_read_model_scopes(...)` still maps upstream write scopes to search refresh targets inside `Application`.
- `search` remains `implementation-gap-open`; no production PostgreSQL/worker/App Status/high-row/browser evidence is claimed.

Next boundary: `read-models:search-refresh-producer-invalidation-boundary-audit`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, grouping, relation or matching business rule changed. |
| 2. Service-layer tests | Applicable | Added `SearchQueryFreshnessServiceTests` for miss, fresh hit and source-version mismatch behavior. |
| 3. API contract tests | Applicable | Reran `/api/search` API and SQL runtime tests to preserve response shape/status behavior. |
| 4. Read model/cache/background job tests | Applicable | Reran search SQL runtime/read model tests covering enqueue-on-miss and source-version behavior. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed and search has no independent frontend page. |
| 6. End-to-end business-flow integration tests | Not applicable | No cross-module write/import/relation flow changed in this slice. |
| 7. Existing feature regression tests | Applicable | Reran search/pending compatibility and manifest tests; added architecture guard preventing app-owned query freshness helpers from returning. |

## State Machine Impact

- `read-models:search-query-freshness-service-extraction` transitions to `implementation-closed`.
- `search` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.
- Global workflow state definitions are unchanged.

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/search_query_freshness_service.py backend/src/fin_ops_platform/services/search_read_model_repository.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_query_freshness_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_rebuild_helpers_stay_out_of_application tests.test_search_pending_sql_runtime.SearchQueryFreshnessServiceTests tests.test_search_pending_sql_runtime.SearchReadModelRepositoryPortTests tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_miss_enqueues_refresh_without_sync_scan tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_reads_sql_index tests.test_search_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_query_freshness_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_rebuild_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
