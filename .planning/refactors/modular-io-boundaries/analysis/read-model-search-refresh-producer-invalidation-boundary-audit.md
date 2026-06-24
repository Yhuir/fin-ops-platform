# Read Model Search Refresh Producer Invalidation Boundary Audit

**Date:** 2026-06-24
**Boundary:** `read-models:search-refresh-producer-invalidation-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit app-owned search refresh producer and invalidation helper ownership after query freshness extraction.

## Evidence Reviewed

- `Application._enqueue_search_read_model_refresh(...)`
- `Application._invalidate_search_read_model_scopes(...)`
- `Application._search_query_freshness_service(...)`
- `Application._handle_api_workbench_settings_update(...)`
- `Application._persist_import_state_with_read_model_invalidation(...)`
- `Application._derived_lifecycle_search_cache_executor(...)`
- `Application._invalidate_workbench_read_model_scopes(...)`
- `SearchQueryFreshnessService`
- `BankDetailReadModelRefreshProducer`
- `TurnoverLedgerReadModelRefreshProducer`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_write_operation_slo_audit.py`
- CodeGraph context and `rg` call-site evidence.

## Findings

| Helper | Classification | Evidence / Decision |
| --- | --- | --- |
| `_enqueue_search_read_model_refresh(...)` | Extractable producer | Thin gateway-backed helper around `ReadModelRefreshGateway.enqueue_one("search", ...)`. Query freshness service and derived lifecycle executor should consume a producer instead of an app helper. |
| `_invalidate_search_read_model_scopes(...)` | Extractable producer invalidation method | Owns search-specific scope normalization for settings/import/workbench invalidation. This belongs with the search refresh producer, not `Application`. |

## Decision

Split and execute `read-models:search-refresh-producer-invalidation-service-extraction` immediately.

The extraction should preserve:

- search scope normalization: month scopes and `all`, fallback to `all`;
- invalidation mapping: exact month scopes or `all` fallback;
- enqueue through `ReadModelRefreshGateway`;
- existing reason/metadata propagation;
- `/api/search` response behavior and worker event/scope policy.

## State Machine Impact

- `read-models:search-refresh-producer-invalidation-boundary-audit` transitions to `analysis-closed`.
- `search` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Implementation verification is recorded in `read-model-search-refresh-producer-invalidation-service-extraction.md`.
