# server-py:bank-details-transaction-categories-route-callback-collapse

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Module closure:** implementation-gap-open

## Scope

Move the disabled bulk bank transaction category PATCH route out of `server.py` and into `BankDetailsApiRoutes.route(...)`.

This slice only covers:

- `PATCH /api/bank-details/transactions/categories`
- removal of `Application._handle_api_bank_transaction_categories(...)`
- preservation of the existing `410 Gone` disabled-response contract
- local tests and static Guard coverage proving the callback cannot silently return to `server.py`

## Implementation

- `backend/src/fin_ops_platform/app/routes_bank_details.py`
  - `BankDetailsApiRoutes.route(...)` now owns `PATCH /api/bank-details/transactions/categories`.
  - The route returns `HTTPStatus.GONE` with `manual_bank_transaction_category_disabled`.
  - The route does not parse JSON, resolve a write session or call `BankDetailsApplicationService`, matching the previous disabled no-mutation behavior.
- `backend/src/fin_ops_platform/app/server.py`
  - Removed the dispatch branch for `PATCH /api/bank-details/transactions/categories`.
  - Removed `_handle_api_bank_transaction_categories(...)`.
- `tests/test_bank_details_routes.py`
  - Added a direct route-owner test proving the disabled PATCH returns 410 and makes no service call.
- `tests/test_platform_runtime_boundary_guards.py`
  - Added the removed handler to the forbidden callback list.
  - Added route-owner markers for the disabled PATCH route and disabled error code.

## Behavior Preserved

- Bulk manual category mutation remains disabled.
- The API response remains `410 Gone`.
- No bank detail category state, read model, dirty scope, outbox, cache, worker, frontend flow or production data path changes.
- No production validation or mutation was executed.

## Docs Impact

- Module implementation notes and test matrix updated.
- Long-term product/API/read-model docs do not change because the public behavior is unchanged and this is an internal route-owner refactor.

## Verification

Passed targeted verification:

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_bank_details.py backend/src/fin_ops_platform/app/server.py tests/test_bank_details_routes.py tests/test_workbench_v2_api.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_routes -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_patch_bank_transaction_categories_is_disabled_and_does_not_mutate_state tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_http_server_dispatches_patch_bank_transaction_categories tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_disabled_manual_clear_does_not_suppress_auto_in_bank_details_api -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_read_export_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered -v`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Remaining Risk

- Bank-details route-owner closure still requires a follow-up audit after this migration.
- Module/global closure is not claimed.
- Real PostgreSQL/worker/App Status/browser/admin/write evidence remains deferred until local implementation and Guard closure are proven.

## Next Boundary

`server-py:bank-details-route-owner-local-closure-audit-retry`
