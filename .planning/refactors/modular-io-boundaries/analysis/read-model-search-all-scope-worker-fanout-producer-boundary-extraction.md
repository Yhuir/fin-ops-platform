# Read Model Search All-Scope Worker Fan-Out Producer Boundary Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:search-all-scope-worker-fanout-producer-boundary-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move `search:all` worker shard fan-out behind `SearchReadModelRefreshProducer` so Search refresh enqueue ownership is consistent across API miss/stale, upstream fan-out, runtime import-state fan-out and worker all-scope expansion.

## Implementation

- `SearchReadModelRefreshProducer` now exposes `enqueue_scope_keys(...)`, returning the normalized enqueued scope keys while preserving `enqueue(...)` boolean behavior for existing callers.
- `SearchReadModelRefreshProducer.normalize_scope_keys(...)` preserves caller order after dedupe so worker all-scope response order remains unchanged.
- `SearchPendingReadModelRefreshService` now accepts optional `search_read_model_refresh_producer`.
- Default construction preserves existing behavior by creating `SearchReadModelRefreshProducer` over the existing `ReadModelRefreshGateway`.
- `_enqueue_search_scope_shards(...)` now calls producer `enqueue_scope_keys(...)` instead of direct `ReadModelRefreshGateway.enqueue_many("search", ...)`.
- Static guard coverage prevents `SearchPendingReadModelRefreshService` from reintroducing direct `enqueue_many("search", ...)`.

## Preserved Behavior

- `search:all` still expands to month shards from `list_search_scope_shards(...)`.
- Returned `enqueued_scope_keys` order remains the shard order returned by the projection builder.
- Search refresh still goes through `ReadModelRefreshGateway`, durable queue and scope policy registry.
- Pending invoice all-scope expansion is unchanged.
- Search API shape, ranking, worker event names, queue schema, Redis/cache behavior, permissions, audit semantics and frontend behavior are unchanged.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No Search business rule changed. |
| 2. Service-layer tests | Applicable | Added worker all-scope producer-boundary test and extended producer contract test. |
| 3. API contract tests | Not applicable | No HTTP/API contract changed. |
| 4. Read model/cache/background job tests | Applicable | Search worker all-scope enqueue ownership changed. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Conditional | Existing Search runtime worker tests cover the fan-out behavior; no browser UI exists for `/api/search`. |
| 7. Existing feature regression tests | Applicable | Preserved existing search all-scope expansion test and updated platform guard. |

## State Machine Impact

- `read-models:search-all-scope-worker-fanout-producer-boundary-extraction` transitions to `implementation-closed`.
- `search` remains `implementation-gap-open`.
- The next boundary is `read-models:search-post-all-scope-worker-fanout-local-implementation-closure-audit`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py tests/test_search_pending_sql_runtime.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchReadModelRefreshProducerTests tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_refresh_handler_expands_search_all_into_month_shards tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_refresh_handler_expands_search_all_through_search_producer_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
python3 -m py_compile backend/src/fin_ops_platform/services/search_read_model_refresh_producer.py backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py backend/src/fin_ops_platform/services/runtime_worker_handlers.py backend/src/fin_ops_platform/services/oa_projection_sync.py backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/search_query_freshness_service.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py tests/test_search_pending_sql_runtime.py tests/test_runtime_worker_read_model_refresh_scopes.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
