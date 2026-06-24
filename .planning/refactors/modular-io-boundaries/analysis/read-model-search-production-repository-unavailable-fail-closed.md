# Read Model Search Production Repository Unavailable Fail Closed

**Date:** 2026-06-24
**Boundary:** `read-models:search-production-repository-unavailable-fail-closed`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Prevent `/api/search` from falling back to legacy/local live search when production PostgreSQL runtime requires SQL read model repository access but the repository is unavailable.

## Implementation

- `_handle_api_search(...)` now checks `_requires_sql_read_model_runtime()` when `SearchQueryFreshnessService.get_payload(...)` returns `None`.
- Production PostgreSQL runtime without a search SQL repository now:
  - enqueues `search:<scope_key>` with reason `api_sql_repository_unavailable`;
  - returns HTTP `503`;
  - returns `error=read_model_unavailable`;
  - returns `read_model_status=unavailable`;
  - does not call `SearchService.search(...)`.
- Legacy/local non-PostgreSQL fallback behavior is unchanged.

## Preserved Behavior

- Existing SQL miss/fresh/stale behavior is unchanged.
- Search ranking, payload shape for fresh SQL/local fallback, worker event names, scope policy, queue schema, Redis/cache, permissions, audit and frontend behavior are unchanged.
- This slice only changes the production PostgreSQL repository-unavailable failure mode.

## Remaining Search Gaps

`search` needs a post-fail-closed local implementation closure audit before it can move to `production-evidence-deferred`.

Next boundary: `read-models:search-post-fail-closed-local-implementation-closure-audit`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, grouping or matching business rule changed. |
| 2. Service-layer tests | Not applicable | This is route/runtime fallback behavior; producer/query services are unchanged. |
| 3. API contract tests | Applicable | Added production repository-unavailable API regression proving fail-closed behavior. |
| 4. Read model/cache/background job tests | Applicable | Test proves missing repository enqueues search refresh instead of live scan. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed; API now exposes non-fresh/unavailable status. |
| 6. End-to-end business-flow integration tests | Not applicable | No business write/import/relation flow changed. |
| 7. Existing feature regression tests | Applicable | Reran search API/runtime regressions to preserve existing local and SQL behavior. |

## State Machine Impact

- `read-models:search-production-repository-unavailable-fail-closed` transitions to `implementation-closed`.
- `search` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py backend/src/fin_ops_platform/services/search_query_freshness_service.py backend/src/fin_ops_platform/services/search_read_model_repository.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_requires_sql_repository_in_production_without_live_scan tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_miss_enqueues_refresh_without_sync_scan tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_reads_sql_index tests.test_search_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_query_freshness_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_rebuild_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
