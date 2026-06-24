# Read Model Search Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:search-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Re-audit `search` after repository port, rebuild helper quarantine, query freshness service extraction and refresh producer extraction.

## Evidence Reviewed

- `Application._handle_api_search(...)`
- `Application._search_query_freshness_service(...)`
- `Application._search_read_model_refresh_producer(...)`
- `SearchReadModelRepositoryPort`
- `SearchQueryFreshnessService`
- `SearchReadModelRefreshProducer`
- `SearchPendingSqlProjectionBuilder`
- `SearchPendingReadModelRefreshService`
- `READ_MODEL_MANIFEST["search"]`
- Runtime worker registry entries for `search`, `search-secondary`, `search-tertiary` and `search-pending`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_search_api.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_read_model_manifest.py`
- `rg` evidence for remaining search-related `Application` call sites.

## Findings

Local support is not ready for production-evidence defer yet.

Remaining implementation gap:

- Production PostgreSQL runtime with missing `search_sql_read_repository` still fell through to legacy/local `SearchService.search(...)`.
- That fallback can live-scan in-memory state instead of returning a non-fresh read model status and enqueuing a durable refresh request.
- This is inconsistent with the read model rule that production pages must not display live fallback data as if read model freshness were proven.

## Decision

Split and execute `read-models:search-production-repository-unavailable-fail-closed`.

## State Machine Impact

- `read-models:search-local-implementation-closure-audit` transitions to `analysis-closed`.
- `search` remains `implementation-gap-open`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Implementation verification is recorded in `read-model-search-production-repository-unavailable-fail-closed.md`.
