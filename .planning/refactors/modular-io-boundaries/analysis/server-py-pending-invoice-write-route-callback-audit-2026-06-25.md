# server-py:pending-invoice-write-route-callback-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit the remaining pending invoice `server.py` callbacks after read/export route callback collapse:

- rules read/update
- attach-existing single/batch preview and confirm
- income-status single/batch update

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
- `backend/src/fin_ops_platform/services/pending_invoice_service.py`
- `backend/src/fin_ops_platform/services/pending_invoice_rules_application_service.py`
- `tests/test_pending_invoice_api.py`
- `docs/modules/pending-invoices/state-machine.md`
- `docs/modules/pending-invoices/tests.md`

## Current Shape

`PendingInvoiceApiRoutes` already owns the service-level methods for the remaining callbacks:

- `rules(...)`
- `update_rules(...)`
- `attach_existing_preview(...)`
- `attach_existing_confirm(...)`
- `attach_existing_batch_preview(...)`
- `attach_existing_batch_confirm(...)`
- `update_income_status(...)`
- `update_income_statuses(...)`

The remaining `Application` callbacks own HTTP adapter concerns:

- read-session auth for rules GET and attach previews;
- write-session auth for rules PUT, attach confirms and income-status updates;
- JSON body parsing;
- mapping `PendingInvoiceError`, `UnauthorizedOASessionError` and `ForbiddenOAAccessError` to HTTP responses;
- calling `_persist_state()` after attach confirm and income-status update success/failure paths that may leave command-log or recoverable state changes.

## Ownership Decision

The next implementation should move the remaining pending invoice HTTP mapping into `PendingInvoiceApiRoutes.route(...)`, but keep platform concerns explicit:

- add a write-session resolver port that returns either `OARequestSession` or an already-mapped HTTP error response;
- reuse the JSON body loader and JSON/error response ports added by Row367;
- add a persist-state port invoked by write routes that currently persist on success and on `PendingInvoiceError`/unexpected exception;
- keep `PendingInvoiceApiRoutes` free of `server.py`, Flask/HTTP response classes, cookie/header parsing and direct persistence implementation;
- keep application/rules services as the owners of business validation, idempotency, command-log recovery, audit and read-model invalidation.

## Next Implementation Slice

`server-py:pending-invoice-write-route-callback-collapse`

Scope:

- route-owner mapping for rules GET/PUT;
- route-owner mapping for attach-existing single/batch preview and confirm;
- route-owner mapping for income-status single/batch update;
- remove migrated app callbacks;
- add/extend static Guard coverage for the remaining pending invoice callbacks;
- preserve all existing API regression tests.

## Stop Gates

- Do not change rules, attach-existing or income-status business behavior.
- Do not remove existing persist-state semantics for confirm/update paths.
- Do not run production validation or mutation.
- Do not claim pending invoice module/global closure.
