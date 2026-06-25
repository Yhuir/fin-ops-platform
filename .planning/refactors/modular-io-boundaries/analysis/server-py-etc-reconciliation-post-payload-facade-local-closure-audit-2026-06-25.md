# server-py:etc-reconciliation-post-payload-facade-local-closure-audit

Date: 2026-06-25
Status: analysis-closed

## Goal

Audit the ETC reconciliation task route-owner surface after payload facade extraction and decide whether this surface is locally closed.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_task_payload_facade.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `EtcReconciliationTaskApiRoutes`, `EtcReconciliationTaskPayloadFacade` and source upload service.

## Findings

The ETC reconciliation task route-owner surface is locally closed:

- `server.py` has no `_handle_api_etc_reconciliation*` callbacks.
- `server.py` no longer defines reconciliation task payload/read-shaping helper implementations.
- `EtcReconciliationTaskApiRoutes` owns task route dispatch and HTTP mapping for list/create/detail/delete/imported-invoice delete/source-file delete/item patch/confirm/reopen/refresh/upload/text.
- `EtcReconciliationTaskPayloadFacade` owns task payload, unavailable payload, import blockers, imported invoice summary, source-file payloads, parse issue payloads and `canConfirm`.
- `EtcReconciliationSourceUploadService` owns source upload and ticket-root text store+parse+apply orchestration.
- `EtcReconciliationImportCleanupService` owns reconciliation import cleanup side effects.
- `Application._etc_reconciliation_routes(...)` now only assembles explicit dependencies and injects callables/services into the route owner.
- The remaining `Application` methods used by this route surface are generic HTTP/error/version/storage/readiness dependencies or shared service factories, not route-specific reconciliation task behavior.

## Guard Evidence

`tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner` now requires:

- route-owner delegation from `handle_request`;
- explicit source upload service injection;
- explicit payload facade assembly;
- explicit import-batch lookup and serializer dependencies for the payload facade;
- no route-owned callback regression into `server.py`;
- no payload helper implementation regression into `server.py`;
- no whole `Application` injection into `EtcReconciliationTaskApiRoutes`.

## Decision

Mark the ETC reconciliation task route-owner surface locally closed for the current modularization pass.

Do not mark the whole ETC module or global modular IO refactor closed. Adjacent ETC/business-batch residual ownership still exists in `server.py`, including `_handle_api_etc_business_batch_delete(...)`, which owns business batch delete orchestration, canonical invoice removal, reconciliation task cleanup, summary relation cancellation and refresh/persist side effects.

Select the next local boundary:

`server-py:etc-business-batch-delete-fallback-audit`

## Verification

No runtime code changed in this analysis slice.

Evidence from the immediately preceding implementation slice:

- py_compile passed for the new facade, `server.py` and affected tests.
- direct facade tests passed.
- route-owner static Guard passed.
- targeted ETC API payload/import/remove regressions passed.
- `bash scripts/verify.sh docs` passed.
- `git diff --check` passed.

## Next Boundary

`server-py:etc-business-batch-delete-fallback-audit`
