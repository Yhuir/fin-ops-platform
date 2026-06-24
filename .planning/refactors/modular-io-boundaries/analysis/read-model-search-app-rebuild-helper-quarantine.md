# Read Model Search App Rebuild Helper Quarantine

**Date:** 2026-06-24
**Boundary:** `read-models:search-app-rebuild-helper-quarantine`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove the unused app-owned search rebuild path so search index rebuild ownership stays with `SearchPendingSqlProjectionBuilder` and worker/runtime boundaries.

## Implementation

- Removed `Application.rebuild_search_index_scope(...)`.
- Removed `Application._build_search_index_rows_for_month(...)`.
- Added `PlatformRuntimeBoundaryGuardTests.test_search_rebuild_helpers_stay_out_of_application`.
- Guard confirms:
  - `server.py` no longer owns the removed search rebuild helpers.
  - `SearchPendingSqlProjectionBuilder` still owns `rebuild_search_index_scope(...)`.
  - Search projection saves through `SearchReadModelRepositoryPort`.

## Preserved Behavior

- No change to `/api/search` route, response shape, freshness/status mapping or fallback behavior.
- No change to `search.read_model.refresh` worker handler or `search:all` fan-out behavior.
- No change to search ranking, searchable text, group context, scope policy, durable queue, Redis/cache, permissions or frontend behavior.

## Remaining Search Gaps

`search` is still not locally closed. Remaining app-owned helpers:

- `_get_search_payload_from_sql_read_model(...)`
- `_search_index_expected_source_versions(...)`
- `_enqueue_search_read_model_refresh(...)`
- `_invalidate_search_read_model_scopes(...)`

Next boundary: `read-models:search-query-freshness-service-extraction`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, grouping, relation, amount or matching business rule changed. |
| 2. Service-layer tests | Applicable | Static guard proves rebuild ownership stays out of `Application` and remains in projection service. |
| 3. API contract tests | Applicable as regression | Search API tests were rerun to prove route behavior and response shape remain stable. |
| 4. Read model/cache/background job tests | Applicable | Search SQL runtime, refresh handler and manifest tests were rerun. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed and no independent search page exists. |
| 6. End-to-end business-flow integration tests | Not applicable | No cross-module write/import/relation flow changed. |
| 7. Existing feature regression tests | Applicable | Search-pending compatibility and manifest tests were rerun. |

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/search_read_model_repository.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_search_rebuild_helpers_stay_out_of_application tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
