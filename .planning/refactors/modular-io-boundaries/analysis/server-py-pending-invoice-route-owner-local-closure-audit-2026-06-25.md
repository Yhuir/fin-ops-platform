# server-py:pending-invoice-route-owner-local-closure-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit pending invoice `Application` surfaces after read/export and write route callback collapse.

## Evidence

- `rg -n "pending_invoice|PendingInvoice" backend/src/fin_ops_platform/app/server.py`
- AST function inventory for `pending_invoice` methods in `server.py`
- `backend/src/fin_ops_platform/app/routes_pending_invoices.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/pending-invoices/state-machine.md`

## Findings

No `_handle_api_pending_invoice*` callback remains in `server.py`.

The remaining pending invoice `Application` surfaces are accounted for as:

- `Application.__init__` dependency wiring for query/application/lifecycle/rules/read-model services;
- `_pending_invoice_routes(...)` route owner factory and composition root;
- `_resolve_pending_invoice_read_session(...)` and `_resolve_pending_invoice_write_session(...)` platform auth/session ports;
- `_pending_invoice_export_response(...)` platform audit/XLSX response port;
- `_pending_invoice_error_response(...)` platform error response mapper;
- `_finalize_pending_invoice_rule_settings_update(...)` app-settings/lifecycle integration port;
- `_import_state_pending_invoice_scope_keys(...)`, `_derived_lifecycle_pending_invoice_executor(...)`, `_pending_invoice_read_model_scope_keys(...)` and `_invalidate_pending_invoice_read_model_scopes(...)` shared read-model invalidation/provider ports;
- `_persist_state(...)` stores `pending_invoice_commands` as part of broad local state persistence.

## Decision

Pending invoice local `server.py` route-owner support is accounted for after:

- Row367 read/export route callback collapse;
- Row369 write route callback collapse;
- existing read-model builder/gate removal guards;
- existing pending invoice service isolation guards.

This is not a pending invoice module closure or global closure. Production PostgreSQL/worker/App Status/browser evidence remains deferred to final validation gates.

## Next Boundary

`server-py:tax-route-owner-audit`
