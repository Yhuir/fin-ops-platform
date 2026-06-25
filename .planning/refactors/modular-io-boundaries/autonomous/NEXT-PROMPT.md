# Next Prompt

Continue after `server-py:etc-reconciliation-upload-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-upload-route-callback-collapse`.
- Row331 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-upload-route-callback-collapse-2026-06-25.md`.
- ETC reconciliation generic upload and ticket-root text HTTP mapping now live in `EtcReconciliationTaskApiRoutes`.
- `server.py` no longer defines `_handle_api_etc_reconciliation_upload(...)` or `_handle_api_etc_reconciliation_ticket_root_texts(...)`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-upload-route-callback-collapse-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` ETC reconciliation factory and residual helper references
   - `backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect residual ETC reconciliation route/helper symbols and callers.
4. Audit only ETC reconciliation route-owner residuals:
   - confirm whether `server.py` still owns reconciliation task route behavior beyond dependency assembly;
   - classify any remaining app-owned helper as removable, service-owned, route-owned, or compat-only;
   - select the next smallest implementation boundary or local closure/defer accounting.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owner or service.
- Do not broaden into unrelated ETC import, legacy batch, invoice or business-batch routes unless the audit proves the reconciliation route owner is locally closed.
