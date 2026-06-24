# Read Model Search Post Runtime Import-State Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:search-post-runtime-import-state-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Re-audit `search` after runtime import-state Search fan-out moved behind `SearchReadModelRefreshProducer`.

## Evidence Reviewed

- `Application._handle_api_search(...)`
- `Application._search_query_freshness_service(...)`
- `Application._search_read_model_refresh_producer(...)`
- `Application._persist_state_with_workbench_invalidation(...)`
- `Application._persist_import_state_with_read_model_invalidation(...)`
- `Application._invalidate_workbench_read_model_scopes(...)`
- `Application._derived_lifecycle_search_cache_executor(...)`
- `SearchReadModelRepositoryPort`
- `SearchQueryFreshnessService`
- `SearchReadModelRefreshProducer`
- `SearchPendingSqlProjectionBuilder`
- `SearchPendingReadModelRefreshService`
- `OAProjectionSyncService._mark_downstream_dirty(...)`
- `_RuntimeWorkerDerivedLifecycle.persist_import_state(...)`
- `READ_MODEL_MANIFEST["search"]`
- Runtime worker registry entries for `search`, `search-secondary`, `search-tertiary`, and `search-pending`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for Search refresh producer ownership.
- `rg` evidence for remaining direct Search refresh enqueue call sites.

## Findings

Local support is not ready for production-evidence defer yet.

Remaining implementation gap:

- `SearchPendingReadModelRefreshService._enqueue_search_scope_shards(...)` still directly created `ReadModelRefreshGateway` and called `enqueue_many("search", shard_keys, reason="search_all_shard")`.
- This path is Search-module-internal worker fan-out and still went through the durable gateway/scope policy registry, so it did not bypass queue safety.
- However, after prior slices declared `SearchReadModelRefreshProducer` the Search refresh enqueue owner, keeping worker `search:all` fan-out on direct gateway leaves a second Search enqueue owner inside the module.

## Decision

Split and execute `read-models:search-all-scope-worker-fanout-producer-boundary-extraction`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, matching, amount, status, permission, or dedupe business rule changed. |
| 2. Service-layer tests | Applicable | Search worker all-scope fan-out needs producer-boundary coverage. |
| 3. API contract tests | Not applicable | No HTTP contract changed. |
| 4. Read model/cache/background job tests | Applicable | This touches `search.read_model.refresh` all-scope fan-out ownership. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Conditional | Existing search runtime worker tests cover the affected all-scope fan-out behavior. |
| 7. Existing feature regression tests | Applicable | Existing search all-scope expansion behavior and static guard coverage need to remain green. |

## State Machine Impact

- `read-models:search-post-runtime-import-state-local-implementation-closure-audit` transitions to `analysis-closed`.
- `search` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Implementation verification is recorded in `read-model-search-all-scope-worker-fanout-producer-boundary-extraction.md`.
