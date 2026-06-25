# Next Prompt

Continue after `server-py:etc-business-oa-draft-revoke-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-business-oa-draft-revoke-route-callback-collapse`.
- Row341 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-oa-draft-revoke-route-callback-collapse-2026-06-25.md`.
- `EtcBusinessBatchApiRoutes` now owns list/create/detail/import/source-files/OA draft/OA draft revoke/manual status/DELETE route mapping for active business-batch routes.
- `EtcBusinessBatchApplicationService` owns business-batch payload workflows, including OA draft create/revoke link/refresh sequencing.
- `EtcBusinessBatchDeleteService` owns business-batch delete side-effect orchestration.
- Literal search finds no `_handle_api_etc_business_*` private callback definition in `server.py` except the active root wrapper `_handle_api_etc_business_batches_route(...)`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-business-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-oa-draft-revoke-route-callback-collapse-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_etc_business_batches_route(...)`
     - `_route_api_etc_business_batch_v2(...)`
     - `_etc_business_routes(...)`
     - `_handle_legacy_etc_batch_business_delete(...)`
     - `_delete_etc_business_batch_via_route_owner(...)`
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_delete_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before any implementation-oriented follow-up.
4. Perform an audit-only boundary first:
   - verify whether active business-batch route-owner local implementation support is now closed;
   - classify remaining app wrappers as route dispatch/session/body/response mapping, compat resolver, or real ownership gap;
   - select the next residual `server.py` boundary outside business-batch if local closure is supported;
   - document tests, docs impact and stop gates.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change runtime behavior during the audit.
- Do not claim whole ETC/global closure from business-batch local closure alone.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
