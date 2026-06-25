# Next Prompt

Continue after `server-py:etc-reconciliation-post-payload-facade-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-post-payload-facade-local-closure-audit`.
- Row335 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-post-payload-facade-local-closure-audit-2026-06-25.md`.
- ETC reconciliation task route-owner surface is locally closed for the current modularization pass.
- Adjacent ETC business-batch delete fallback ownership still lives in `Application`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-business-batch-delete-fallback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-post-payload-facade-local-closure-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_etc_business_batch_delete(...)`
     - `_route_api_etc_business_batch_v2(...)`
     - `_handle_api_etc_business_batches_route(...)`
     - `_handle_legacy_etc_batch_business_delete(...)`
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py`
   - relevant business batch delete tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect callers/callees for business batch delete and legacy fallback paths.
4. Audit only the business batch delete fallback boundary:
   - identify whether delete orchestration belongs in `EtcBusinessBatchApiRoutes`, `EtcBusinessBatchApplicationService`, a dedicated delete service, or remains a documented compat wrapper;
   - preserve idempotency, submitted reset, relation cancellation, canonical invoice cleanup, reconciliation task tombstone and refresh/persist semantics;
   - select the next smallest implementation boundary.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change runtime code unless the audit finds a narrow residual local implementation gap.
- Do not change business batch delete semantics.
- Do not change reconciliation task tombstone or summary relation cancellation semantics.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
