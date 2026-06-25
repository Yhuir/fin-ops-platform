# server-py:etc-business-batch-delete-service-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Goal

Move ETC business-batch delete side-effect orchestration out of `Application` into an explicit service while preserving HTTP response shape and existing delete semantics.

## Files Changed

- `backend/src/fin_ops_platform/services/etc_business_batch_delete_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_etc_business_batch_delete_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `.planning/refactors/modular-io-boundaries/autonomous/*`
- `docs/modules/etc-tickets/implementation-notes.md`

## Implementation

Added `EtcBusinessBatchDeleteService` with explicit dependencies:

- `etc_service`;
- `import_service`;
- `reconciliation_task_service`;
- `cleanup_service`;
- `existing_etc_invoices_by_ids`;
- `etc_invoice_changed_months`;
- `link_etc_invoices_to_existing_invoices`;
- `assert_etc_summary_relation_write_precondition_for_batch`;
- `cancel_etc_summary_relations_for_batch`.

The service now owns:

- business batch lookup and idempotent missing-batch fallback;
- invoice/import-batch id collection;
- linked reconciliation task lookup;
- changed-month calculation;
- relation freshness preflight for submitted business batches;
- `EtcService.delete_business_batch(...)`;
- submitted reset relation cancellation and relinking;
- canonical ETC invoice cleanup by import batch;
- reconciliation task cleanup after business batch delete;
- explicit refresh/persist event decisions.

`Application._handle_api_etc_business_batch_delete(...)` is now a thin HTTP body/error/response mapper:

- parses JSON body;
- computes `expectedVersion` and reason;
- calls `_etc_business_batch_delete_service().delete_business_batch(...)`;
- executes returned refresh/persist events;
- maps the existing delete result payload to `_etc_business_response(...)`.

The service does not receive `Application`, does not read HTTP headers/cookies, and does not construct HTTP responses.

## Tests Added Or Changed

- Added `tests/test_etc_business_batch_delete_service.py` with direct service coverage for:
  - unsubmitted/import-backed business batch delete canonical invoice cleanup and refresh/persist event;
  - submitted business batch reset relation preflight/cancel/relink/cleanup;
  - missing business id idempotent fallback.
- Updated static Guard so relation preflight/cancel/task cleanup ownership is checked in the new service and the app callback must delegate side-effect orchestration.
- Preserved targeted API regressions for submitted delete, legacy submission delete delegation, relation cancellation and stale business id idempotency.

## Verification

Passed:

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_business_batch_delete_service.py backend/src/fin_ops_platform/app/server.py tests/test_etc_business_batch_delete_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_business_batch_delete_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_summary_relation_delete_uses_workbench_relation_command_boundary -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_releases_summary_and_deletes_local_task tests.test_etc_backend.EtcApiTests.test_legacy_submission_batch_delete_delegates_to_business_batch_reset tests.test_etc_backend.EtcApiTests.test_submitted_etc_business_batch_delete_cancels_summary_relation_without_restoring_oa_bank_pair tests.test_etc_backend.EtcApiTests.test_etc_business_batch_delete_is_idempotent_for_stale_business_ids -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcServiceTests.test_business_batch_delete_resets_submitted_batch_and_releases_invoices tests.test_etc_backend.EtcServiceTests.test_business_batch_delete_is_idempotent_and_hides_deleted_batch tests.test_etc_backend.EtcServiceTests.test_business_batch_delete_removes_unsubmitted_oa_draft_contents -v`

## Seven Test Category Decision

- Business core unit tests: covered through direct service tests for delete/reset/idempotent fallback.
- Service-layer tests: covered by the new delete service tests.
- API contract tests: covered by targeted ETC API delete regressions.
- Read model/cache/background job tests: not directly applicable; this slice preserves existing refresh/persist event calls but does not change read model queue/freshness code.
- Frontend component and interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: partially covered by backend API flow regressions for submitted delete and legacy submission delete.
- Existing feature regression tests: covered by static Guard and existing ETC backend delete regressions.

## Docs Impact

Updated ETC tickets implementation notes and modular IO autonomous state files. Product/API long-term docs are unchanged because response shape and business semantics are unchanged.

## Remaining Risk

`Application._handle_api_etc_business_batch_delete(...)` remains as a thin callback and `_handle_legacy_etc_batch_business_delete(...)` still delegates to it. The next local boundary should audit whether this thin callback can collapse into `EtcBusinessBatchApiRoutes` or a route owner port.

## Next Boundary

`server-py:etc-business-batch-delete-route-callback-collapse-audit`
