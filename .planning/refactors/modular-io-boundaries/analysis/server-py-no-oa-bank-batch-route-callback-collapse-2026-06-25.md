# server-py:no-oa-bank-batch-route-callback-collapse

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Module closure:** implementation-gap-open

## Scope

Collapse no-OA bank batch HTTP route callbacks from `server.py` into `NoOaBankBatchApiRoutes.route(...)`.

This slice covers only `/api/no-oa-bank-batches*` HTTP dispatch, path parsing, mutation session/body loading ports and JSON response mapping.

## Implementation

- `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
  - Added `NoOaBankBatchApiRoutes.route(...)`.
  - Added explicit ports:
    - `resolve_mutation_session`
    - `load_json_body`
    - `json_response`
  - Moved exact and dynamic route matching into the route owner.
  - Preserved existing route methods and application-service ownership for list/detail/tag-selection/submit/withdraw/submit-selection/bulk-submit behavior.
- `backend/src/fin_ops_platform/app/server.py`
  - Delegates all `/api/no-oa-bank-batches*` dispatch to `self._no_oa_bank_batch_routes().route(method, route_path, query, body, headers)`.
  - Removed eight app-owned no-OA route callbacks:
    - `_handle_api_no_oa_bank_batches`
    - `_handle_api_no_oa_bank_batch_tag_selection`
    - `_handle_api_no_oa_bank_batch_tag_selection_update`
    - `_handle_api_no_oa_bank_batch_detail`
    - `_handle_api_no_oa_bank_batch_submit`
    - `_handle_api_no_oa_bank_batch_withdraw`
    - `_handle_api_no_oa_bank_batches_bulk_submit`
    - `_handle_api_no_oa_bank_batches_submit_selection`
- `tests/test_no_oa_bank_batch_routes.py`
  - Added route-owner HTTP mapping/port coverage.
  - Added session/body error short-circuit coverage.
- `tests/test_platform_runtime_boundary_guards.py`
  - Added a static Guard preventing no-OA route callbacks from returning to `server.py`.
  - Guard confirms route owner has the expected route markers and does not own persistence/queue side effects.

## Behavior Preserved

- Public API shape is unchanged.
- Permission/session behavior is unchanged.
- Invalid JSON/body errors still return before service calls.
- Unknown batch, persistence error, value error and relation freshness conflict mapping remains owned by `NoOaBankBatchApiRoutes`.
- Relation command side effects, read-model refresh enqueue, dirty/outbox writes, persistence/rollback, source-version and stale-reason calculations remain outside route code.
- No production validation or mutation was executed.

## Verification

Passed:

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py backend/src/fin_ops_platform/app/server.py tests/test_no_oa_bank_batch_routes.py tests/test_no_oa_bank_batch_api.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_routes -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_routes_delegate_to_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`
- `rg -n "def _handle_api_no_oa_bank_batch|/api/no-oa-bank-batches|_no_oa_bank_batch_routes\\(\\)\\.route" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Remaining Risk

- No no-OA route-owner closure audit has run after this migration.
- No no-OA module/global closure is claimed.
- Real PostgreSQL/worker/App Status/browser/admin/write evidence remains deferred until local implementation gaps are accounted for.

## Next Boundary

`server-py:no-oa-bank-batch-route-owner-local-closure-audit`
