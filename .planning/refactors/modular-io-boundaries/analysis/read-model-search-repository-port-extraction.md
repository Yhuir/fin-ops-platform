# Read Model Search Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:search-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Add a narrow repository port for the `search` read model so `/api/search` SQL reads and search projection saves no longer require the broad `PostgresReadModelRepository` surface.

## Evidence Reviewed

- `docs/modules/search/README.md`
- `docs/modules/search/state-machine.md`
- `docs/modules/search/tests.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-no-oa-bank-batch.md`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_search_api.py`
- `tests/test_read_model_manifest.py`
- CodeGraph context for `search_index`, `save_search_index_rows`, `SearchPendingSqlProjectionBuilder`, `_get_search_payload_from_sql_read_model`, and `_search_sql_read_repository`.

## Implementation

- Added `SearchReadModelRepositoryPort`.
- `SearchReadModelRepositoryPort` exposes only:
  - `search_index(...)`
  - `save_search_index_rows(...)`
- `PostgresStateStore.search_sql_read_repository` now returns `SearchReadModelRepositoryPort` over the optional SQL read connection.
- `SearchPendingSqlProjectionBuilder.rebuild_search_index_scope(...)` now saves search index rows through `SearchReadModelRepositoryPort`.
- `READ_MODEL_MANIFEST["search"].repository_owner` is now `SearchReadModelRepositoryPort`.
- Added a port guard test proving unrelated pending invoice, bank detail, no-OA and workbench relation methods are not exposed.

## Preserved Behavior

- No change to `/api/search` request parameters, response shape, status codes, permission behavior or fallback semantics.
- No change to search ranking, group context, source fact selection or searchable text construction.
- No change to `search.read_model.refresh`, `search:all` fan-out semantics, scope policy, durable queue schema, Redis/cache behavior, RabbitMQ behavior or worker lanes.
- No Go/Fiber/Go Worker work.

## Remaining Search Gaps

`search` is not locally closed. The next slice should audit app-owned helper contamination:

- `Application._get_search_payload_from_sql_read_model(...)`
- `Application._search_index_expected_source_versions(...)`
- `Application._enqueue_search_read_model_refresh(...)`
- `Application.rebuild_search_index_scope(...)`
- `Application._build_search_index_rows_for_month(...)`
- `Application._invalidate_search_read_model_scopes(...)`

The next boundary is `read-models:search-freshness-helper-boundary-audit`.

## State Machine Impact

- `read-models:search-repository-port-extraction` transitions to `implementation-closed`.
- `search` remains `implementation-gap-open`.
- Global and module state definitions are unchanged; only execution accounting and implementation notes change.
- Go/Fiber/Go Worker admission remains blocked.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No search ranking, grouping, amount, relation, invoice or bank business rule changed. |
| 2. Service-layer tests | Applicable | Added `SearchReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`. |
| 3. API contract tests | Applicable as regression | Reran `tests.test_search_api` and search API SQL read model tests to preserve shape/status. |
| 4. Read model/cache/background job tests | Applicable | Reran search projection, refresh handler, manifest and gateway-adjacent search runtime tests. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed and `/api/search` has no independent frontend route. |
| 6. End-to-end business-flow integration tests | Not applicable | No import/relation/write flow changed. |
| 7. Existing feature regression tests | Applicable | Reran search/pending SQL runtime and manifest tests to protect search-pending compatibility. |

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/search_read_model_repository.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/read_model_manifest.py
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime tests.test_search_api tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
