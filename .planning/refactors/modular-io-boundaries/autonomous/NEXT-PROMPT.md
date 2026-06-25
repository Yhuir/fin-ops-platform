# Next Prompt

Continue after `server-py:etc-business-batch-delete-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-business-batch-delete-route-callback-collapse`.
- Row339 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-delete-route-callback-collapse-2026-06-25.md`.
- `EtcBusinessBatchDeleteService` owns business-batch delete side-effect orchestration.
- `EtcBusinessBatchApiRoutes.delete_batch(...)` owns business-batch DELETE HTTP body/error/response mapping and executes returned refresh/persist events through explicit ports.
- `_handle_api_etc_business_batch_delete(...)` is removed from `server.py`.
- Legacy `/api/etc/batches/{id}` business-batch delete compatibility is preserved through `_delete_etc_business_batch_via_route_owner(...)`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-business-oa-draft-revoke-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-delete-route-callback-collapse-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_etc_business_oa_draft_revoke(...)`
     - `_route_api_etc_business_batch_v2(...)`
     - `_etc_business_routes(...)`
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
   - relevant OA draft/revoke tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect callers/callees for OA draft revoke and related business-batch route owner methods.
4. Perform an audit-only boundary first:
   - classify whether `_handle_api_etc_business_oa_draft_revoke(...)` is route mapping, service orchestration, or mixed ownership;
   - identify the smallest safe next implementation slice;
   - decide whether existing application service should own revoke behavior or whether a new explicit service/port is needed;
   - document tests, docs impact and stop gates.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change OA draft revoke behavior during the audit.
- Do not move OA token/header parsing into a service.
- Do not pass the whole `Application` into `EtcBusinessBatchApiRoutes`.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
