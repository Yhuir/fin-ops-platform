# Next Prompt

Continue after `server-py:etc-business-oa-draft-revoke-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-business-oa-draft-revoke-callback-audit`.
- Row340 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-oa-draft-revoke-callback-audit-2026-06-25.md`.
- `EtcService.revoke_business_batch_oa_draft(...)` owns the core OA draft revoke state transition, version check, idempotency, invoice release, audit event and persistence.
- `Application._handle_api_etc_business_oa_draft_revoke(...)` still owns HTTP mapping plus direct service/link/refresh sequencing.
- `EtcBusinessBatchApplicationService.create_oa_draft_payload(...)` already owns the symmetric OA draft create workflow and has explicit link/refresh ports.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-business-oa-draft-revoke-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-oa-draft-revoke-callback-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_etc_business_oa_draft_revoke(...)`
     - `_route_api_etc_business_batch_v2(...)`
     - `_etc_business_routes(...)`
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
   - `backend/src/fin_ops_platform/services/etc_service.py` around `revoke_business_batch_oa_draft(...)`
   - relevant OA draft/revoke tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect callers/callees for OA draft revoke and related business-batch route owner methods.
4. Implement the callback collapse:
   - add `EtcBusinessBatchApplicationService.revoke_oa_draft_payload(...)`;
   - keep core transition in `EtcService.revoke_business_batch_oa_draft(...)`;
   - reuse application-service link/refresh sequencing for `etc_business_oa_draft_revoked`;
   - add `EtcBusinessBatchApiRoutes.revoke_oa_draft(...)`;
   - make `_route_api_etc_business_batch_v2(...)` delegate `oa-draft/revoke` to route owner;
   - remove `_handle_api_etc_business_oa_draft_revoke(...)` from `server.py`;
   - extend static Guard and run targeted OA draft/revoke API/service regressions.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change OA draft revoke behavior, audit event, idempotency, version conflict handling or response shape.
- Do not move OA token/header parsing into a service.
- Do not pass the whole `Application` into route owner or application service.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
