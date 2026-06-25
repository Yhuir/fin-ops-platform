# server-py:etc-business-batch-delete-route-callback-collapse

**Status:** local-implementation-closed
**Date:** 2026-06-25
**Previous boundary:** `server-py:etc-business-batch-delete-route-callback-collapse-audit`
**Next boundary:** `server-py:etc-business-oa-draft-revoke-callback-audit`

## Goal

Collapse the now-thin ETC business-batch DELETE HTTP callback out of `Application` and into `EtcBusinessBatchApiRoutes`, while keeping delete side-effect orchestration in `EtcBusinessBatchDeleteService` and preserving legacy `/api/etc/batches/{id}` business-batch compatibility.

## Implementation

- Extended `EtcBusinessBatchApiRoutes` with explicit ports:
  - `delete_service`;
  - `load_json_body`;
  - `refresh_after_etc_invoice_link`;
  - `persist_state`.
- Added `EtcBusinessBatchApiRoutes.delete_batch(...)` to own DELETE body parsing, delete service delegation, returned refresh/persist event execution, and ETC business-batch error/success envelope mapping.
- Removed `_handle_api_etc_business_batch_delete(...)` from `server.py`.
- Changed `_route_api_etc_business_batch_v2(...)` DELETE to authenticate mutation access and delegate to `EtcBusinessBatchApiRoutes.delete_batch(...)`.
- Kept legacy batch business-delete compatibility through `_delete_etc_business_batch_via_route_owner(...)`, so legacy routing remains an explicit resolver and does not regain side-effect ownership.
- Moved `WorkbenchRelationCommandError` API mapping into `routes_etc.py` to preserve the previous conflict response contract.

## Boundary Evidence

- `server.py` no longer defines `_handle_api_etc_business_batch_delete(...)`.
- `server.py` still performs dependency wiring, mutation-session check for the v2 DELETE path, and final HTTP response conversion.
- Business delete side effects remain in `EtcBusinessBatchDeleteService.delete_business_batch(...)`.
- Route owner receives explicit dependencies; it does not receive `Application`.
- Static Guard now prevents the old delete callback from returning and checks that route owner delete delegates to the delete service and executes returned refresh/persist events.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_summary_relation_delete_uses_workbench_relation_command_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_business_batch_routes_do_not_keep_removed_legacy_handlers -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_releases_summary_and_deletes_local_task tests.test_etc_backend.EtcApiTests.test_legacy_submission_batch_delete_delegates_to_business_batch_reset tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_cancels_summary_relation_without_restoring_oa_bank_pair tests.test_etc_backend.EtcApiTests.test_etc_business_batch_delete_is_idempotent_for_stale_business_ids -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_business_batch_delete_service -v`

## Docs Impact

Only modular IO state files and ETC implementation notes changed. Product/API long-term facts did not change because response shape and business behavior were preserved.

## Remaining Risk

- Production browser/admin/write validation remains a final validation gate and was not run for this local-only slice.
- ETC business-batch OA draft revoke callback still lives in `Application`; audit it next before claiming local business-batch route-owner closure.
