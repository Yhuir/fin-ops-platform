# Next Prompt

Continue after `server-py:etc-business-batch-delete-service-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-business-batch-delete-service-extraction`.
- Row337 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-delete-service-extraction-2026-06-25.md`.
- `EtcBusinessBatchDeleteService` now owns business-batch delete side-effect orchestration.
- `_handle_api_etc_business_batch_delete(...)` remains as a thin HTTP mapper in `Application`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-business-batch-delete-route-callback-collapse-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-delete-service-extraction-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_etc_business_batch_delete(...)`
     - `_route_api_etc_business_batch_v2(...)`
     - `_handle_api_etc_business_batches_route(...)`
     - `_handle_legacy_etc_batch_business_delete(...)`
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_delete_service.py`
   - relevant business batch delete tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect callers/callees for the thin delete callback and legacy fallback.
4. Audit whether the thin business-batch DELETE callback can collapse into `EtcBusinessBatchApiRoutes`:
   - preserve body parsing, error mapping, refresh/persist event execution and response shape;
   - preserve `_handle_legacy_etc_batch_business_delete(...)` semantics;
   - decide whether route owner needs a delete service port and refresh/persist ports.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change business batch delete semantics.
- Do not change reconciliation task tombstone or summary relation cancellation semantics.
- Do not change runtime code unless the audit finds a narrow route callback collapse slice.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
