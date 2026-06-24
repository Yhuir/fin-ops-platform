# Read Model Search Post OA Projection Sync Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:search-post-oa-projection-sync-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Re-audit `search` after OA projection sync Search fan-out moved behind `SearchReadModelRefreshProducer`.

## Evidence Reviewed

- `Application._handle_api_search(...)`
- `Application._search_query_freshness_service(...)`
- `Application._search_read_model_refresh_producer(...)`
- `SearchReadModelRepositoryPort`
- `SearchQueryFreshnessService`
- `SearchReadModelRefreshProducer`
- `SearchPendingSqlProjectionBuilder`
- `SearchPendingReadModelRefreshService`
- `OAProjectionSyncService._mark_downstream_dirty(...)`
- `_RuntimeWorkerDerivedLifecycle.persist_import_state(...)`
- `_RuntimeWorkerDerivedLifecycle._enqueue_scopes(...)`
- `READ_MODEL_MANIFEST["search"]`
- Runtime worker registry entries for `search`, `search-secondary`, `search-tertiary`, and `search-pending`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `rg` evidence for remaining Search refresh enqueue call sites.

## Findings

Local support is not ready for production-evidence defer yet.

Remaining implementation gap:

- `_RuntimeWorkerDerivedLifecycle.persist_import_state(...)` still used the generic `_enqueue_scopes("search", ..., reason="import_state_changed")` path.
- This path still went through `ReadModelRefreshGateway` and the scope policy registry, but it bypassed the Search-specific `SearchReadModelRefreshProducer`.
- Import-state fan-out is one of the highest-frequency Search refresh producers. Leaving it generic would keep Search refresh ownership split after the OA projection sync producer extraction.

## Decision

Split and execute `read-models:search-runtime-import-state-refresh-producer-boundary-extraction`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No import parsing, search ranking, matching, amount, status, permission, or dedupe business rule changed. |
| 2. Service-layer tests | Applicable | Runtime import-state lifecycle fan-out needs Search producer delegation coverage. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Applicable | This touches runtime worker `search.read_model.refresh` enqueue ownership. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Conditional | Existing import-state worker integration tests cover the affected fan-out behavior. |
| 7. Existing feature regression tests | Applicable | Existing import-state scope tests and Search producer static guard need to remain green. |

## State Machine Impact

- `read-models:search-post-oa-projection-sync-local-implementation-closure-audit` transitions to `analysis-closed`.
- `search` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Implementation verification is recorded in `read-model-search-runtime-import-state-refresh-producer-boundary-extraction.md`.
