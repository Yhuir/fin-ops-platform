# server-py:etc-invoice-route-owner-audit

## Status

`local-implementation-closed`

## Goal

Move residual `/api/etc/invoices` and `/api/etc/invoices/revoke-submitted` HTTP ownership out of `Application` without changing ETC invoice business behavior.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc.py`
- `backend/src/fin_ops_platform/app/routes_etc_import.py`
- `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/services/etc_service.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Implementation

- Added `EtcInvoiceApiRoutes` in `backend/src/fin_ops_platform/app/routes_etc_invoices.py`.
- Moved GET invoice list and POST revoke-submitted HTTP mapping from `server.py` into the route owner.
- `server.py` now delegates `/api/etc/invoices` and `/api/etc/invoices/revoke-submitted` through `_etc_invoice_routes().route(...)`.
- Removed app-owned `_handle_api_etc_invoices(...)` and `_handle_api_etc_revoke_submitted(...)`.
- Preserved `Application._serialize_etc_invoice(...)` as an injected serialization port because legacy batch read facade and other app assembly paths still share the attachment-existence payload contract.
- Preserved status mutation in `EtcService.revoke_submitted(...)` and preserved existing link/refresh behavior through explicit ports.

## Boundary Result

`server.py` no longer owns ETC invoice list/revoke HTTP callback bodies. It owns only dependency assembly and top-level route dispatch.

`EtcInvoiceApiRoutes` does not receive `Application`, does not import auth/server/cookies, and does not know SQL table structure. It uses explicit ports for JSON response, body parsing, invoice serialization, ETC invoice linking, and read-model refresh.

## Tests

- Added route-owner inventory coverage for recently added ETC route owner files.
- Added `test_etc_invoice_routes_delegate_to_route_owner` to prevent app-owned invoice callbacks from returning and to guard explicit route-owner ports.
- Reused existing ETC invoice/revoke API regressions.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_invoices.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_invoice_routes_delegate_to_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_import_query_revoke_and_batch_api_round_trip tests.test_etc_backend.EtcApiTests.test_api_returns_clear_errors_for_invalid_input tests.test_etc_backend.EtcApiTests.test_old_direct_import_no_longer_persists_records -v`

## Next Boundary

`server-py:etc-reconciliation-task-mutation-callback-audit`

Reason: `EtcReconciliationTaskApiRoutes` still receives upload, supplement, ticket-root text/file delete, item patch, confirm, reopen and refresh-match callbacks from `Application`. The next safe local boundary is to audit those callbacks and decide whether to move HTTP ownership into the route owner or extract narrower services first.
