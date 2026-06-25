# server-py:etc-business-oa-draft-revoke-route-callback-collapse

**Status:** local-implementation-closed
**Date:** 2026-06-25
**Previous boundary:** `server-py:etc-business-oa-draft-revoke-callback-audit`
**Next boundary:** `server-py:etc-business-route-owner-local-closure-audit`

## Goal

Move ETC business-batch OA draft revoke HTTP ownership out of `Application`, preserving the existing `EtcService.revoke_business_batch_oa_draft(...)` state transition and API response contract.

## Implementation

- Added `EtcBusinessBatchApplicationService.revoke_oa_draft_payload(...)`.
- Kept core revoke behavior in `EtcService.revoke_business_batch_oa_draft(...)`.
- Reused application-service scoped access checks and canonical invoice link/refresh sequencing for `etc_business_oa_draft_revoked`.
- Added `EtcBusinessBatchApiRoutes.revoke_oa_draft(...)`.
- Updated `_route_api_etc_business_batch_v2(...)` to parse JSON and delegate `oa-draft/revoke` to the route owner.
- Removed `_handle_api_etc_business_oa_draft_revoke(...)` from `server.py`.
- Extended the static route-owner Guard to prevent the old callback from returning and require revoke delegation.
- Added API regression coverage for `POST /api/etc/business-batches/{id}/oa-draft/revoke`.

## Boundary Evidence

- Literal search now finds no `_handle_api_etc_business_oa_draft_revoke(...)` definition in `server.py`.
- `server.py` keeps only route dispatch, session handling, JSON parsing and response conversion for this path.
- Application-service method owns access scoping plus link/refresh side effect.
- Route owner owns payload-to-application-service mapping and ETC business response/error shape.
- Core state transition, idempotency, audit event and persistence remain in `EtcService`.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/etc_business_batch_application_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_business_batch_routes_do_not_keep_removed_legacy_handlers -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcServiceTests.test_business_batch_supplement_merge_rejects_after_draft_and_allows_after_revoke tests.test_etc_backend.EtcServiceTests.test_business_batch_revoke_is_idempotent_and_releases_invoices tests.test_etc_backend.EtcApiTests.test_etc_business_batch_oa_draft_revoke_route_resets_batch_and_invoices tests.test_etc_backend.EtcApiTests.test_etc_business_batch_api_and_legacy_batches_use_unified_view -v`

## Docs Impact

Only modular IO state files and ETC implementation notes changed. Product/API long-term facts did not change because response shape and business behavior were preserved.

## Remaining Risk

- Production browser/admin/write validation remains a final validation gate and was not run for this local-only slice.
- A local closure audit is still needed to verify the ETC business-batch route-owner surface has no remaining app-owned private callback or helper ownership gaps.
