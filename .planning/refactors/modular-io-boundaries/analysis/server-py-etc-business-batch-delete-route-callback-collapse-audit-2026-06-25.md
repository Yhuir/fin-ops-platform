# server-py:etc-business-batch-delete-route-callback-collapse-audit

Date: 2026-06-25
Status: analysis-closed

## Goal

Audit the now-thin ETC business-batch DELETE callback after `EtcBusinessBatchDeleteService` extraction and decide whether it can collapse into `EtcBusinessBatchApiRoutes`.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc.py`
- `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
- `backend/src/fin_ops_platform/services/etc_business_batch_delete_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_etc_backend.py`
- CodeGraph context for `EtcBusinessBatchApiRoutes`, `EtcBusinessBatchApplicationService` and legacy batch routes.

## Findings

`Application._handle_api_etc_business_batch_delete(...)` is now thin:

- parses optional JSON body;
- extracts `expectedVersion` and reason;
- calls `_etc_business_batch_delete_service().delete_business_batch(...)`;
- executes returned refresh/persist events;
- maps errors through `_etc_business_error_response(...)`;
- maps success through `_etc_business_response(...)`.

The side-effect orchestration no longer lives in `Application`; it is owned by `EtcBusinessBatchDeleteService`.

This callback can move into `EtcBusinessBatchApiRoutes` if the route owner receives explicit ports:

- `delete_service`;
- `load_json_body`;
- `refresh_after_etc_invoice_link`;
- `persist_state`.

The route owner already has `_success(...)`, `_error_response(...)` and `_optional_int(...)`, so it can preserve the existing `{ok,data,error,requestId}` envelope without importing `Application`.

`_handle_legacy_etc_batch_business_delete(...)` still exists because the legacy `/api/etc/batches/{batch_id}` route may receive a submission/import/linked id and needs to translate it to a business batch delete. This should remain as a small compatibility resolver or be renamed to a port such as `_delete_linked_business_batch_from_legacy_batch(...)`. It should not own delete side effects.

## Decision

Select the next local implementation boundary:

`server-py:etc-business-batch-delete-route-callback-collapse`

Scope:

- Extend `EtcBusinessBatchApiRoutes.__init__(...)` with explicit delete service, JSON loader and refresh/persist ports.
- Add `EtcBusinessBatchApiRoutes.delete_batch(...)` to own DELETE HTTP mapping.
- Change `_route_api_etc_business_batch_v2(...)` DELETE branch to authenticate mutation session and delegate to route owner.
- Keep `_handle_legacy_etc_batch_business_delete(...)` temporarily as a compat resolver that delegates to a business-route delete port or helper.
- Remove `_handle_api_etc_business_batch_delete(...)` from `server.py`.
- Extend static Guard to prevent the callback from returning.

## Stop Gates For Implementation

- Do not change business batch DELETE response shape.
- Do not change legacy submission batch delete delegation behavior.
- Do not change relation preflight/cancel, canonical cleanup or reconciliation task cleanup semantics.
- Do not pass `Application` into `EtcBusinessBatchApiRoutes`.
- Do not move delete side-effect orchestration back into route code.
- Do not run production validation or mutation.

## Required Tests For Next Slice

- Keep direct `EtcBusinessBatchDeleteService` tests.
- Extend static route-owner Guard for business-batch DELETE delegation.
- Run targeted business-batch DELETE API regressions:
  - submitted delete releases summary and deletes local task;
  - legacy submission batch delete delegates to business batch reset;
  - summary relation cancellation regression;
  - stale business id idempotency.

## Verification

Analysis-only slice. No runtime code changed.

## Next Boundary

`server-py:etc-business-batch-delete-route-callback-collapse`
