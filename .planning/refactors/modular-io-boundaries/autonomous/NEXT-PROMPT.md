# Next Prompt

Continue after `server-py:etc-business-batch-delete-fallback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-business-batch-delete-fallback-audit`.
- Row336 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-delete-fallback-audit-2026-06-25.md`.
- `_handle_api_etc_business_batch_delete(...)` still owns broad business-batch delete side-effect orchestration in `Application`.
- The next slice should extract a dedicated delete service before route callback collapse.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-business-batch-delete-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-delete-fallback-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_etc_business_batch_delete(...)`
     - `_route_api_etc_business_batch_v2(...)`
     - `_handle_api_etc_business_batches_route(...)`
     - `_handle_legacy_etc_batch_business_delete(...)`
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/etc_service.py` business batch delete methods
   - `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py`
   - relevant business batch delete tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect callers/callees for business batch delete and legacy fallback paths.
4. Extract business-batch delete side-effect orchestration into a dedicated service:
   - service receives explicit dependencies only;
   - service returns explicit delete result plus refresh/persist events;
   - `Application._handle_api_etc_business_batch_delete(...)` becomes a thin HTTP body/error/response mapper for this slice;
   - preserve legacy business delete fallback callers.
5. Add direct service tests and extend static Guard.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change business batch delete semantics.
- Do not change reconciliation task tombstone or summary relation cancellation semantics.
- Do not pass the whole `Application` into the service.
- Do not move HTTP response construction into the service.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
