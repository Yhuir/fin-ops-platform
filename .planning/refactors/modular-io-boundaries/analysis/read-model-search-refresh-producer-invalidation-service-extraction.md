# Read Model Search Refresh Producer Invalidation Service Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:search-refresh-producer-invalidation-service-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move search refresh enqueue and invalidation scope normalization out of `Application` into an explicit producer.

## Implementation

- Added `SearchReadModelRefreshProducer`.
- Removed `Application._enqueue_search_read_model_refresh(...)`.
- Removed `Application._invalidate_search_read_model_scopes(...)`.
- `SearchQueryFreshnessService` now receives `SearchReadModelRefreshProducer.enqueue_one`.
- Settings update, import-state invalidation, Workbench invalidation and derived lifecycle search cache invalidation now call `SearchReadModelRefreshProducer`.

## Preserved Behavior

- Refresh enqueue still goes through `ReadModelRefreshGateway`.
- Scope type remains `search`.
- Existing reason and metadata propagation are preserved.
- Search query API, ranking, payload shape, worker event names, scope policy, queue schema, Redis/cache, permissions, audit and frontend behavior are unchanged.

## Remaining Search Gaps

`search` still needs a local implementation closure audit. The next audit must confirm whether any remaining local implementation gaps exist after repository port, rebuild helper quarantine, query freshness extraction and refresh producer extraction.

Next boundary: `read-models:search-local-implementation-closure-audit`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, grouping, relation or matching rule changed. |
| 2. Service-layer tests | Applicable | Added `SearchReadModelRefreshProducerTests` for enqueue normalization, invalidation mapping and unavailable gateway behavior. |
| 3. API contract tests | Applicable as regression | Reran `/api/search` API/runtime tests to preserve response shape and miss/fresh behavior. |
| 4. Read model/cache/background job tests | Applicable | Producer tests prove search refresh requests still use gateway-owned scope enqueue; runtime worker/manifest tests are rerun in full verification. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed and search has no independent frontend page. |
| 6. End-to-end business-flow integration tests | Not applicable | No business write flow changed; settings/import/workbench invalidation call sites keep existing reason/metadata behavior. |
| 7. Existing feature regression tests | Applicable | Platform guard prevents app-owned refresh helpers from returning; search runtime/API tests preserve existing behavior. |

## State Machine Impact

- `read-models:search-refresh-producer-invalidation-service-extraction` transitions to `implementation-closed`.
- `search` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py backend/src/fin_ops_platform/services/search_query_freshness_service.py backend/src/fin_ops_platform/services/search_read_model_repository.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_query_freshness_helpers_stay_out_of_application tests.test_search_pending_sql_runtime.SearchReadModelRefreshProducerTests tests.test_search_pending_sql_runtime.SearchQueryFreshnessServiceTests tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_miss_enqueues_refresh_without_sync_scan tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_reads_sql_index tests.test_search_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_query_freshness_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_rebuild_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
