# Read Model Search OA Projection Sync Refresh Producer Boundary Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:search-oa-projection-sync-refresh-producer-boundary-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move OA projection sync's Search refresh fan-out behind `SearchReadModelRefreshProducer` so Search refresh enqueue ownership is not split across generic upstream services.

## Implementation

- `OAProjectionSyncService` now accepts `search_read_model_refresh_producer`.
- When the dependency is not supplied, it builds a `SearchReadModelRefreshProducer` over the existing `ReadModelRefreshGateway(queue_repository=...)`, preserving existing constructor compatibility.
- `_mark_downstream_dirty(...)` now calls `SearchReadModelRefreshProducer.enqueue(target_scopes, reason="oa_projection_sync")` instead of directly calling `refresh_gateway.enqueue_many("search", ...)`.
- The production worker assembly now passes an explicit `SearchReadModelRefreshProducer` to `OAProjectionSyncService`.
- Static guard coverage now prevents `OAProjectionSyncService` from reintroducing a direct `enqueue_many("search", ...)` bypass.

## Preserved Behavior

- OA sync still computes the same downstream `target_scopes`.
- Existing Workbench, OA pending payment, and pending invoice refresh enqueue behavior is unchanged.
- Search refresh still goes through `ReadModelRefreshGateway`, durable queue, and scope policy registry.
- Search API shape, ranking, worker event names, queue schema, Redis/cache behavior, permissions, audit semantics, and frontend behavior are unchanged.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, grouping, matching, amount, status, permission, or dedupe business rule changed. |
| 2. Service-layer tests | Applicable | Added `OaProjectionSyncServiceTests.test_oa_sync_search_refresh_uses_search_producer_boundary`. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Applicable | Existing OA projection SQL runtime test confirms downstream Search dirty scope behavior remains. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Conditional | Existing OA sync runtime integration coverage exercises the affected worker fan-out path. |
| 7. Existing feature regression tests | Applicable | Existing OA sync dirty fan-out and Search runtime boundary guard coverage were run. |

## State Machine Impact

- `read-models:search-oa-projection-sync-refresh-producer-boundary-extraction` transitions to `implementation-closed`.
- `search` remains `implementation-gap-open`.
- The next boundary is `read-models:search-post-oa-projection-sync-local-implementation-closure-audit`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/oa_projection_sync.py backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_projection_sync_service.OaProjectionSyncServiceTests.test_oa_sync_search_refresh_uses_search_producer_boundary tests.test_oa_projection_sync_service.OaProjectionSyncServiceTests.test_oa_sync_marks_oa_pending_payment_read_model_dirty_for_progress_rows tests.test_oa_projection_sql_runtime.OAProjectionSqlRuntimeTests.test_oa_sync_worker_persists_projection_and_marks_downstream_scopes_dirty tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
python3 -m py_compile backend/src/fin_ops_platform/services/oa_projection_sync.py backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py backend/src/fin_ops_platform/services/search_query_freshness_service.py backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
