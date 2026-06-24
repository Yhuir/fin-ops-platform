# Read Model Search Freshness Helper Boundary Audit

**Date:** 2026-06-24
**Boundary:** `read-models:search-freshness-helper-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit remaining app-owned search helper surfaces after repository port extraction, then split and execute the first concrete narrow implementation gap.

## Evidence Reviewed

- `Application._get_search_payload_from_sql_read_model(...)`
- `Application._search_index_expected_source_versions(...)`
- `Application._enqueue_search_read_model_refresh(...)`
- `Application.rebuild_search_index_scope(...)`
- `Application._build_search_index_rows_for_month(...)`
- `Application._invalidate_search_read_model_scopes(...)`
- `SearchPendingSqlProjectionBuilder.rebuild_search_index_scope(...)`
- `SearchReadModelRepositoryPort`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_search_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph callers/impact for `_get_search_payload_from_sql_read_model`, `Application.rebuild_search_index_scope`, and `_build_search_index_rows_for_month`.

## Findings

| Helper | Classification | Evidence / Decision |
| --- | --- | --- |
| `_get_search_payload_from_sql_read_model(...)` | Implementation gap remains | Still owns search API fresh/stale/miss payload assembly, source-version mismatch handling and enqueue reasons. Should move to a service/facade in a later slice. |
| `_search_index_expected_source_versions(...)` | Implementation gap remains | Still app-owned because it reads app settings/OA source versions; should move with the search query/freshness service or a source-version provider. |
| `_enqueue_search_read_model_refresh(...)` | Dependency assembly / implementation gap remains | Enqueue uses `ReadModelRefreshGateway`; behavior is correct, but app still owns the producer helper. Can be extracted with search query/freshness service or refresh producer. |
| `_invalidate_search_read_model_scopes(...)` | Implementation gap remains | Still maps upstream write scopes to search refresh targets in `Application`; should be audited after query/freshness service extraction. |
| `Application.rebuild_search_index_scope(...)` | Removable old path | CodeGraph found no callers. Worker already uses `SearchPendingSqlProjectionBuilder.rebuild_search_index_scope(...)`. |
| `Application._build_search_index_rows_for_month(...)` | Removable old path | Only called by the removed app-level rebuild helper. |

## Decision

Split and execute `read-models:search-app-rebuild-helper-quarantine` as the first implementation gap from this audit.

The remaining query/freshness/enqueue/invalidation helpers are not safe to remove in this slice because `/api/search`, settings/import fan-out and workbench invalidation still call them. The next boundary should be `read-models:search-query-freshness-service-extraction`.

## State Machine Impact

- `read-models:search-freshness-helper-boundary-audit` transitions to `analysis-closed`.
- `search` remains `implementation-gap-open`.
- No global workflow state definitions changed.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

The audit's implementation split was verified in `read-models:search-app-rebuild-helper-quarantine`.
