# Batch Accounting GET Route Owner Extraction

**Date:** 2026-06-24
**Boundary:** `batch-accounting:legacy-route-implementation`
**Status:** implementation slice closed; module implementation gap remains open

## Scope

This slice converts the read-only `GET /api/batch-accounting` handler from a `server.py` inline route body into a dedicated route owner:

- `Application._handle_api_batch_accounting(...)` now delegates to `BatchAccountingApiRoutes.list_payload(...)`.
- `BatchAccountingApiRoutes` owns query parameter normalization and `BatchAccountingError` to HTTP payload/status mapping for the list endpoint.
- `BatchAccountingService.build_payload(..., use_sql_read_model=True)` remains the read contract owner.

The slice intentionally does not change submit/withdraw mutation behavior, API response shape, pagination semantics, permission semantics, read model freshness semantics, or frontend behavior.

## Boundary Contract

### Input

- HTTP query map from `GET /api/batch-accounting`.
- Supported aliases remain unchanged:
  - `year`
  - `bank_year`
  - `oa_year`
  - `bucket`
  - `page`
  - `page_size` / `pageSize`
  - `bank_page` / `bankPage`
  - `bank_page_size` / `bankPageSize`
  - `oa_page` / `oaPage`
  - `oa_page_size` / `oaPageSize`

### Output

- Successful response remains the existing `BatchAccountingService.build_payload(...)` dictionary.
- `batch_accounting_version_conflict` remains HTTP `409`.
- Other `BatchAccountingError` codes remain HTTP `400`.
- Error payload still includes `error`, `message`, and structured `exc.payload`.

### State And Events

- `GET /api/batch-accounting` remains read-only.
- The route owner must not repair legacy relations, write canonical relations, enqueue read model refreshes, schedule lifecycle jobs, or emit mutation events.
- Submit/withdraw mutation state transitions remain in the existing `BatchAccountingService` boundary and are deliberately left for a later side-effect route boundary slice.

### Read Model

- Read model access remains through `BatchAccountingService.build_payload(..., use_sql_read_model=True)`.
- The route owner does not read SQL, cache, dirty scope tables, worker queues, or relation repositories directly.
- Existing read model status fields and stale diagnostics remain service-owned.

### Permissions

- This slice does not change auth/session/permission behavior.
- `server.py` continues to own HTTP registration and dependency wiring.

### Tests

- Static guard now proves `routes_batch_accounting.py` is registered in the route owner inventory.
- Static guard now proves `GET /api/batch-accounting` delegates to `BatchAccountingApiRoutes` and the route owner delegates to `BatchAccountingService` with SQL read model enabled.
- Existing API tests prove list payload, pagination, no legacy repair on GET, and stale relation read model status are preserved.

## Impact Analysis

### Positive Impact

- Reduces `server.py` business/read-model route body ownership.
- Makes batch-accounting GET route IO explicit and easier to test as a dedicated owner.
- Preserves the earlier guard-only contract while converting part of it into actual implementation.

### Unchanged

- Submit route remains in `server.py`.
- Withdraw route remains in `server.py`.
- `_batch_accounting_error_response(...)` remains in `server.py` because submit/withdraw still use it.
- `_repair_batch_accounting_relation_case_ids(...)` remains explicit compat/repair path and must not be called from GET.

### Remaining Gaps

- `batch-accounting` is not module-closed.
- Submit/withdraw HTTP DTO and error mapping still need a route owner or side-effect port boundary.
- Production DB/worker evidence is not required for this local route-owner extraction because no production state, queue, or SQL behavior changed.

## Verification

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_uses_sql_read_model_loader_when_available tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_does_not_run_legacy_relation_repair tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_explicit_pagination_protects_first_screen_slo tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_exposes_relation_read_model_missing_status -v`
- `git diff --check`

