# Read Model Search Post Fail-Closed Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:search-post-fail-closed-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Re-audit `search` after production PostgreSQL repository-unavailable fail-closed behavior.

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
- `READ_MODEL_MANIFEST["search"]`
- Runtime worker registry entries for `search`, `search-secondary`, `search-tertiary`, and `search-pending`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_search_api.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `rg` evidence for remaining `enqueue_many("search", ...)` call sites.

## Findings

Local support is not ready for production-evidence defer yet.

Remaining implementation gap:

- `OAProjectionSyncService._mark_downstream_dirty(...)` still directly called `ReadModelRefreshGateway.enqueue_many("search", target_scopes, reason="oa_projection_sync")`.
- This did not bypass the durable gateway or scope policy, but it bypassed the explicit `SearchReadModelRefreshProducer` owner introduced for search refresh enqueue and scope normalization.
- Because OA projection sync is a canonical upstream fact fan-out for Search source versions, leaving this direct call would keep one Search refresh producer path outside the Search module boundary.

## Decision

Split and execute `read-models:search-oa-projection-sync-refresh-producer-boundary-extraction`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, matching, grouping, amount, or status business rules changed. |
| 2. Service-layer tests | Applicable | OA sync downstream dirty fan-out now needs to prove Search producer delegation. |
| 3. API contract tests | Not applicable | `/api/search` request/response shape and status mapping are unchanged. |
| 4. Read model/cache/background job tests | Applicable | This touches `search.read_model.refresh` enqueue ownership from an upstream worker. |
| 5. Frontend component and interaction tests | Not applicable | No frontend page or interaction behavior changed. |
| 6. End-to-end business-flow integration tests | Conditional | OA sync -> downstream read model fan-out is covered by existing service/runtime integration tests in this slice. |
| 7. Existing feature regression tests | Applicable | Existing OA sync downstream dirty behavior and Search producer guard need regression coverage. |

## State Machine Impact

- `read-models:search-post-fail-closed-local-implementation-closure-audit` transitions to `analysis-closed`.
- `search` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Implementation verification is recorded in `read-model-search-oa-projection-sync-refresh-producer-boundary-extraction.md`.
