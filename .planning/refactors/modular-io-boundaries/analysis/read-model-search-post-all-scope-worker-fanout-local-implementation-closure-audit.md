# Read Model Search Post All-Scope Worker Fan-Out Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:search-post-all-scope-worker-fanout-local-implementation-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Goal

Re-audit `search` after `search:all` worker shard fan-out moved behind `SearchReadModelRefreshProducer`.

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
- `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY["search"]`
- Runtime worker registry entries for `search`, `search-secondary`, `search-tertiary`, and `search-pending`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_search_api.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for Search refresh/repository ownership.
- `rg` evidence for remaining Search helper, live fallback, direct refresh enqueue and rebuild call sites.

## Findings

No remaining local implementation gap was found after the all-scope worker fan-out producer extraction.

Local support currently accounted:

- IO contract: `/api/search` parameter validation and payload assembly remain in the route, while SQL freshness/status/source-version behavior is delegated to `SearchQueryFreshnessService`.
- Public/internal boundary: `/api/search` is the public API; repository access is behind `SearchReadModelRepositoryPort`; projection rebuild is owned by `SearchPendingSqlProjectionBuilder`.
- Canonical fact owner: Search index is derived from source rows and must not become canonical fact storage.
- Shared fact source: source-version proof is owned by `SearchIndexSourceVersionsProvider`; Workbench/import/OA/settings fan-out uses registered refresh boundaries.
- Read model contract: manifest declares `partitioned_scoped_index`, `search.read_model.refresh`, `fan_out_command` all-scope semantics and `SearchReadModelRepositoryPort`.
- Freshness proof: `SearchQueryFreshnessService` returns fresh/stale/refreshing/unavailable based on SQL payload, expected source versions and repository availability.
- Force refresh contract: non-transactional refresh requests go through `SearchReadModelRefreshProducer` and `ReadModelRefreshGateway`.
- Operation barrier contract: manifest/App Status registry covers the `search` read model; no independent page-level operation barrier UI exists.
- Legacy removal/quarantine: app-owned rebuild helpers, query freshness helpers and refresh/invalidation helpers are removed and guarded. Production PostgreSQL repository-unavailable behavior fails closed instead of live scanning.
- Permission contract: Search remains owned by the API session boundary; this slice did not change permissions.
- Audit contract: This slice did not change audited business writes.
- Test contract: Search API/runtime/manifest/worker/static guard tests cover local contracts.

Classified retained local compatibility:

- `Application._handle_api_search(...)` can still call `SearchService.search(...)` only when `_requires_sql_read_model_runtime()` is false. This is a local/legacy compatibility path and is guarded by the production fail-closed regression.
- `SearchPendingReadModelRefreshService` still also handles `pending_invoice.read_model.refresh` for the compatibility `search-pending` worker lane. It is registered and covered by worker/manifest tests; it must not become a new Search owner.

## Deferred Evidence

The following cannot be proven from the current local environment without production/staging PostgreSQL and worker evidence:

- Real PostgreSQL `search` SQL read repository readiness.
- Durable dirty/outbox drain for `search.read_model.refresh`.
- App Status readiness/stale/failure transitions after real worker drain.
- High-row search index rebuild and query performance.
- Browser/user-flow smoke evidence for pages that invoke `/api/search`, if a UI entry exists in production.

These are recorded as `production-evidence-deferred`. This is not a global module closure.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, matching, amount, status, permission, or dedupe rule changed. |
| 2. Service-layer tests | Existing coverage applies | Repository port, freshness service, refresh producer and worker service tests cover the local service contracts. |
| 3. API contract tests | Existing coverage applies | Search API tests cover grouped results/status filtering/read model fallback behavior; production repository-unavailable fail-closed is covered. |
| 4. Read model/cache/background job tests | Existing coverage applies | Worker fan-out, stale source-version skip, `search:all` shard expansion, manifest and registry tests cover local contracts. |
| 5. Frontend component and interaction tests | Not applicable | `/api/search` currently has no independent frontend page in this module; future global search UI must add frontend/E2E coverage. |
| 6. End-to-end business-flow integration tests | Deferred evidence | Local runtime tests cover critical fan-out behavior, but real PostgreSQL/worker/browser evidence is deferred. |
| 7. Existing feature regression tests | Existing coverage applies | Search API, search/pending compatibility worker, manifest/registry and platform guard tests remain the regression net. |

## State Machine Impact

- `read-models:search-post-all-scope-worker-fanout-local-implementation-closure-audit` transitions to `production-evidence-deferred`.
- `search` moves from local `implementation-gap-open` to `not-module-closed`.
- Insert next boundary: `read-models:next-pilot-selection-after-search`.
- Go/Fiber/Go Worker admission remains blocked until the next non-Go read model candidate is selected and accounted.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_oa_projection_sync_service tests.test_oa_projection_sql_runtime tests.test_runtime_worker_read_model_refresh_scopes tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_enqueues_workbench_month_scopes_before_all_aggregate tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_import_state_invalidation_skips_unaffected_invoice_relation_read_models tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_refresh_producer_helpers_stay_out_of_application -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
