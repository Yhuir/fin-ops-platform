# Next Prompt

Continue after `server-py:etc-reconciliation-task-mutation-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-task-mutation-callback-audit`.
- Row323 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-mutation-callback-audit-2026-06-25.md`.
- Row323 classified residual reconciliation callbacks into simple task mutations and upload/parser-heavy flows.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-simple-mutation-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-mutation-callback-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` `_etc_reconciliation_routes(...)` and simple mutation callbacks
   - targeted ETC reconciliation task tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph to inspect callers/callees for:
   - `_handle_api_etc_reconciliation_source_file_delete`
   - `_handle_api_etc_reconciliation_item_patch`
   - `_handle_api_etc_reconciliation_confirm`
   - `_handle_api_etc_reconciliation_reopen`
   - `_handle_api_etc_reconciliation_refresh_matches`
   - `EtcReconciliationTaskApiRoutes`
4. Implement only the simple mutation callback collapse:
   - move source-file delete, item patch, confirm, reopen and refresh-match HTTP bodies into `EtcReconciliationTaskApiRoutes`;
   - remove the corresponding app-owned callbacks from `server.py`;
   - keep upload/parser-heavy callbacks unchanged;
   - update static Guard coverage and targeted regressions.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not move upload, supplement, ticket-root text, object-storage, parser or source-mode detection flows in this slice.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owners or services.
- Keep read model refresh through existing explicit freshness/enqueue boundaries.
