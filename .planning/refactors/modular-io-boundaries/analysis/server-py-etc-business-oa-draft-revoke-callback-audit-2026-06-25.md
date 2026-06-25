# server-py:etc-business-oa-draft-revoke-callback-audit

**Status:** analysis-closed
**Date:** 2026-06-25
**Previous boundary:** `server-py:etc-business-batch-delete-route-callback-collapse`
**Next boundary:** `server-py:etc-business-oa-draft-revoke-route-callback-collapse`

## Goal

Audit the remaining ETC business-batch OA draft revoke callback in `Application` and select the smallest safe local implementation boundary that keeps `server.py` thin.

## Current Ownership

`Application._handle_api_etc_business_oa_draft_revoke(...)` currently owns:

- JSON body parsing;
- `expectedVersion` / `expected_version` parsing;
- direct `EtcService.revoke_business_batch_oa_draft(...)` call;
- canonical invoice re-link after revoke;
- `_refresh_after_etc_invoice_link(..., reason="etc_business_oa_draft_revoked")`;
- ETC business-batch response envelope mapping.

The callback is active through `_route_api_etc_business_batch_v2(...)` for `POST /api/etc/business-batches/{id}/oa-draft/revoke`.

## Evidence

- `EtcService.revoke_business_batch_oa_draft(...)` owns the core state transition, version check, invoice release, audit event and persistence.
- `EtcBusinessBatchApplicationService.create_oa_draft_payload(...)` already owns the symmetric create-draft workflow and receives explicit ports for OA client construction, canonical invoice linking and refresh.
- `EtcBusinessBatchApiRoutes` already owns `create_oa_draft(...)`, `manual_oa_status(...)`, import preview/confirm, detail, list/create and DELETE mapping after Row339.
- No new SQL/repository/read-model boundary is needed for revoke. The post-revoke refresh should stay behind the existing `link_etc_invoices_to_existing_invoices` / `refresh_after_etc_invoice_link` ports already accepted by `EtcBusinessBatchApplicationService`.

## Decision

Select `server-py:etc-business-oa-draft-revoke-route-callback-collapse`.

The implementation should:

- add `EtcBusinessBatchApplicationService.revoke_oa_draft_payload(...)`;
- keep the core revoke transition in `EtcService.revoke_business_batch_oa_draft(...)`;
- reuse `_link_existing_canonical_invoices(batch, "etc_business_oa_draft_revoked")` or equivalent service-owned link/refresh sequencing;
- add `EtcBusinessBatchApiRoutes.revoke_oa_draft(...)` for route-owned HTTP mapping;
- make `_route_api_etc_business_batch_v2(...)` delegate `oa-draft/revoke` to the route owner;
- remove `_handle_api_etc_business_oa_draft_revoke(...)` from `server.py`;
- extend static Guard to prevent the old callback from returning.

## Tests To Run Next

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/etc_business_batch_application_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_business_batch_routes_do_not_keep_removed_legacy_handlers -v`
- Targeted ETC service/API revoke and OA draft regressions from `tests/test_etc_backend.py`, including:
  - `EtcServiceTests.test_business_batch_supplement_merge_rejects_after_draft_and_allows_after_revoke`
  - `EtcServiceTests.test_business_batch_revoke_is_idempotent_and_releases_invoices`
  - relevant business-batch OA draft/API round-trip tests that hit `/api/etc/business-batches/{id}/oa-draft`.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Gates

- Do not change OA draft revoke business behavior, audit event, idempotency, version conflict handling or response shape.
- Do not move OA token/header parsing into a service.
- Do not pass `Application` into `EtcBusinessBatchApiRoutes` or `EtcBusinessBatchApplicationService`.
- Do not introduce direct SQL/read-model writes.
- Do not run production browser/admin/write validation for this local slice.

## Docs Impact

Only modular IO state files and ETC implementation notes need updates for this audit. Product/API long-term facts are unchanged.
