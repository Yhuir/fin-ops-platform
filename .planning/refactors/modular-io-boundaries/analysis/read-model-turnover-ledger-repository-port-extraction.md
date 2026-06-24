# Read Model Turnover Ledger Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:turnover-ledger-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`turnover_ledger` was selected as the tenth non-Go read model implementation pilot after `cost_statistics`. The first narrow implementation boundary was to isolate the manifest-listed turnover read model repository methods before auditing freshness, force refresh, operation barriers and legacy contamination.

## Implemented Boundary

- Added `TurnoverLedgerReadModelRepositoryPort`.
- The port exposes only:
  - `list_turnover_ledger_view`;
  - `save_turnover_ledger_rows`;
  - `clear_turnover_ledger_rows`.
- `PostgresStateStore.turnover_ledger_sql_read_repository` now returns the narrow port over the optional SQL read connection.
- `Application._initialize_runtime_services(...)` wires `TurnoverLedgerQueryService` to the turnover-specific port instead of the broad workbench SQL read repository.
- `worker.py` passes the narrow turnover port into `TurnoverLedgerSqlProjectionBuilder`.
- Added a unit guard proving unrelated read model methods are not exposed by the turnover port.

## Non-Goals

- No turnover business rule changes.
- No grouped payload, API shape, permission, audit, queue schema, worker event name, Redis envelope or frontend behavior changes.
- No SQL ownership move out of `PostgresReadModelRepository`.
- No Go/Fiber/Go Worker work.

## Legacy And Boundary Classification

- `PostgresReadModelRepository` remains the SQL/table owner.
- Broad `workbench_sql_read_repository` remains for its existing workbench/search/legacy consumers, but it no longer owns production turnover query injection.
- Local tests may still use test doubles with broader methods where needed; production turnover read/write read model paths now receive the narrow port.
- This slice does not prove turnover freshness/barrier closure or remove every app-owned helper. Those checks are the next boundary.

## Seven-Category Test Decision

1. Business core unit tests: not applicable; no turnover amount, closure, relation, tag or extra rule changed.
2. Service-layer tests: applicable; added `TurnoverLedgerReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`.
3. API contract tests: not applicable for this slice; no HTTP shape/status/error/permission change.
4. Read model/cache/background job tests: applicable; reran turnover query and refresh tests covering fresh/stale/missing and worker refresh behavior.
5. Frontend component and interaction tests: not applicable; no frontend/API mapper/operation overlay behavior changed.
6. End-to-end business-flow integration tests: not applicable; repository port extraction does not change confirm/withdraw/tag-selection flows.
7. Existing feature regression tests: applicable; targeted turnover query/refresh tests and the new port guard protect existing behavior while narrowing the production wiring.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/turnover_ledger_read_model_repository.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/worker.py tests/test_turnover_ledger_query_service.py tests/test_turnover_ledger_read_model_refresh.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_read_model_refresh -v`

## State Impact

- Queue item `141` moves to `implementation-closed`.
- `turnover_ledger` remains `implementation-gap-open`.
- Insert next boundary: `read-models:turnover-ledger-refresh-freshness-operation-barrier-audit`.
- Go/Fiber/Go Worker admission remains blocked.

## Remaining Risk

- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- Turnover fresh gate, force refresh, all fan-out/query proof, Workbench relation source-version proof, operation barrier targets, legacy read contamination and app-owned helper classification are not closed by this slice.

## Next Boundary

`read-models:turnover-ledger-refresh-freshness-operation-barrier-audit`
