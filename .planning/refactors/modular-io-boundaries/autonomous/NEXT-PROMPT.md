# Next Prompt

Continue after `server-py:etc-invoice-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-invoice-route-owner-audit`.
- Row322 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-invoice-route-owner-audit-2026-06-25.md`.
- Row322 added `EtcInvoiceApiRoutes` and moved ETC invoice list/revoke-submitted HTTP mapping out of `Application`.
- `server.py` now assembles the ETC invoice route owner with explicit JSON/body/serializer/link/refresh ports.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-task-mutation-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-invoice-route-owner-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` `_etc_reconciliation_routes(...)` factory and remaining `_handle_api_etc_reconciliation_*` callbacks
   - `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - targeted ETC reconciliation task tests in `tests/test_etc_backend.py`
3. Use CodeGraph to inspect callers/callees for `EtcReconciliationTaskApiRoutes`, `_etc_reconciliation_routes`, `_handle_api_etc_reconciliation_upload`, `_handle_api_etc_reconciliation_confirm`, `_handle_api_etc_reconciliation_reopen`, `_handle_api_etc_reconciliation_item_patch`, `_handle_api_etc_reconciliation_refresh_matches`, ticket-root text/file handlers and supplement upload.
4. Decide whether the next safe implementation is:
   - moving remaining reconciliation task mutation HTTP handlers into `EtcReconciliationTaskApiRoutes` with explicit ports;
   - extracting a narrower upload/source-file/service boundary first;
   - or closing an analysis-only slice if callback coupling is too broad.
5. Update analysis/state and add or update tests for any accepted implementation.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owners or services.
- Do not change business-batch v2 behavior.
- Keep cleanup behavior in `EtcReconciliationImportCleanupService` unless the selected boundary explicitly proves a narrower service move.
- Keep read model refresh through existing explicit freshness/enqueue boundaries.
