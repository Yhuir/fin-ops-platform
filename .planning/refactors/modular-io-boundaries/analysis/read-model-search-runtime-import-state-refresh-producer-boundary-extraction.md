# Read Model Search Runtime Import-State Refresh Producer Boundary Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:search-runtime-import-state-refresh-producer-boundary-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move runtime import-state Search refresh fan-out behind `SearchReadModelRefreshProducer` so high-frequency import worker refresh ownership is consistent with the Search module boundary.

## Implementation

- `_RuntimeWorkerDerivedLifecycle` now accepts optional `search_read_model_refresh_producer`.
- Default construction preserves existing behavior by creating `SearchReadModelRefreshProducer` over the existing `ReadModelRefreshGateway`.
- `persist_import_state(...)` now calls `SearchReadModelRefreshProducer.enqueue(...)` for Search scopes instead of generic `_enqueue_scopes("search", ...)`.
- Static guard coverage prevents runtime worker handlers from reintroducing `_enqueue_scopes("search", ...)` or direct `enqueue_many("search", ...)`.

## Preserved Behavior

- Import-state target scopes are unchanged.
- Search refresh still goes through `ReadModelRefreshGateway`, durable queue, and scope policy registry.
- Workbench, Workbench relation, invoice lifecycle, pending invoice, invoice usage, OA pending payment, bank detail, bank account balance, cost statistics, and tax offset fan-out behavior is unchanged.
- Search API shape, ranking, worker event names, queue schema, Redis/cache behavior, permissions, audit semantics, and frontend behavior are unchanged.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No import or search business rule changed. |
| 2. Service-layer tests | Applicable | Added runtime lifecycle producer-boundary test. |
| 3. API contract tests | Not applicable | No HTTP/API contract changed. |
| 4. Read model/cache/background job tests | Applicable | Runtime import-state Search refresh enqueue ownership changed. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Conditional | Existing Workbench SQL runtime tests cover import-state fan-out contracts. |
| 7. Existing feature regression tests | Applicable | Runtime worker scope tests and platform boundary guards were updated/run. |

## State Machine Impact

- `read-models:search-runtime-import-state-refresh-producer-boundary-extraction` transitions to `implementation-closed`.
- `search` remains `implementation-gap-open`.
- The next boundary is `read-models:search-post-runtime-import-state-local-implementation-closure-audit`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_worker_handlers.py backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py tests/test_runtime_worker_read_model_refresh_scopes.py tests/test_platform_runtime_boundary_guards.py
python3 -m py_compile backend/src/fin_ops_platform/services/runtime_worker_handlers.py backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py backend/src/fin_ops_platform/services/oa_projection_sync.py backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/search_query_freshness_service.py backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py tests/test_runtime_worker_read_model_refresh_scopes.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
