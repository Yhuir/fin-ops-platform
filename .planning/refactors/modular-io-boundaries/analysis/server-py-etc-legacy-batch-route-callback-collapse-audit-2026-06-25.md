# server-py:etc-legacy-batch-route-callback-collapse-audit

## Status

`local-implementation-closed`

## Goal

Collapse the remaining legacy `/api/etc/batches*` HTTP callbacks out of `Application` after the prior delete service, lifecycle service, and read facade slices made the side-effect and payload ownership explicit.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/etc_legacy_batch_read_facade.py`
- `backend/src/fin_ops_platform/services/etc_legacy_batch_delete_service.py`
- `backend/src/fin_ops_platform/services/etc_legacy_batch_lifecycle_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- Targeted legacy ETC batch API regressions in `tests/test_etc_backend.py`

## Implementation

- `EtcLegacyBatchApiRoutes` now owns legacy batch list, detail, non-business delete, draft creation, batch draft creation, confirm submitted, and mark-not-submitted HTTP mapping directly.
- `server.py` now injects explicit route-owner ports: JSON response, JSON body loader, reconciliation error mapper, read facade, delete service, lifecycle service, OA client builder, business-batch legacy delete fallback, refresh callback, and persistence callback.
- Removed the old app-owned legacy batch callbacks:
  - `_handle_api_etc_batches`
  - `_handle_api_etc_batch_detail`
  - `_handle_api_etc_batch_delete`
  - `_handle_api_etc_batch_draft`
  - `_handle_api_etc_batch_draft_for_batch`
  - `_create_etc_batch_draft_from_invoice_ids`
  - `_handle_api_etc_batch_confirm_submitted`
  - `_handle_api_etc_batch_mark_not_submitted`
- Kept business-batch v2 delete behavior behind the narrow `legacy_business_delete` port so Row321 does not change `/api/etc/business-batches*` semantics.

## Boundary Result

`server.py` no longer owns legacy batch HTTP callback bodies. It only assembles dependencies and delegates `/api/etc/batches*` dispatch to `EtcLegacyBatchApiRoutes`.

The route owner does not receive `Application`, does not construct services, and does not own SQL. Business behavior remains in `EtcLegacyBatchDeleteService`, `EtcLegacyBatchLifecycleService`, `EtcLegacyBatchReadFacade`, and the existing business-batch v2 delete path.

## Tests

- Updated runtime boundary guards so they protect the new route-owner/service/facade port contract and prevent the removed callbacks from returning to `server.py`.
- Reused existing ETC API regressions for delete, draft, confirm, list, query and detail behavior.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_routes_delegate_to_compat_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_delete_side_effects_use_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_lifecycle_side_effects_use_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_read_payload_uses_facade_boundary -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_delete_etc_batch_route_deletes_unsubmitted_and_submitted tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_cascades_mutable_batch_contents tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_repairs_stale_invoice_references tests.test_etc_backend.EtcApiTests.test_unsubmitted_oa_draft_batch_is_listed_and_deletable tests.test_etc_backend.EtcApiTests.test_delete_missing_unsubmitted_oa_draft_batch_repairs_reconciliation_task_link tests.test_etc_backend.EtcApiTests.test_reconciliation_import_batch_route_creates_oa_draft tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_oa_draft_uploads_supplements_and_uses_oa_total tests.test_etc_backend.EtcApiTests.test_confirming_reconciliation_backed_oa_submission_finalizes_task tests.test_etc_backend.EtcApiTests.test_api_returns_clear_errors_for_invalid_input tests.test_etc_backend.EtcApiTests.test_etc_batch_query_api_returns_counts_summary_plate_summary_and_items tests.test_etc_backend.EtcApiTests.test_etc_batch_list_only_checks_attachment_status_for_selected_detail tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_submitted_batch_detail_includes_supplement_metadata -v`

## Next Boundary

`server-py:etc-invoice-route-owner-audit`

Reason: residual ETC dispatch still has `/api/etc/invoices` and `/api/etc/invoices/revoke-submitted` directly handled in `Application`. This is the next smaller local-first route-owner boundary before production validation.
