# server.py ETC reconciliation task delete side-effect service audit

- Date: 2026-06-25
- Boundary: `server-py:etc-reconciliation-task-delete-side-effect-service-audit`
- Status: `analysis-closed`
- Module closure: `implementation-gap-open`
- Production: not used

## Scope

This slice audited the `Application` callbacks still injected into `EtcReconciliationTaskApiRoutes` for task deletion and imported-invoice deletion. It did not change runtime code.

## Evidence Read

- `analysis/server-py-etc-reconciliation-task-route-owner-facade-extraction-2026-06-25.md`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for ETC reconciliation task service and related ETC batch/link services.

## Current Residual Surface

`EtcReconciliationTaskApiRoutes` delegates these two callbacks back to `Application`:

- `_handle_api_etc_reconciliation_imported_invoices_delete(...)`
- `_handle_api_etc_reconciliation_task_delete(...)`

Those callbacks share a deeper cleanup cluster:

- `_remove_reconciliation_task_imported_invoices(...)`
- `_delete_reconciliation_task_unsubmitted_submission_batch(...)`
- `_delete_reconciliation_task_import_batch_sources(...)`
- `_reconciliation_task_business_batch_for_import(...)`
- `_delete_reconciliation_task_business_batch_sources(...)`
- `_delete_etc_import_batch_sources(...)`
- `_clear_reconciliation_task_import_after_batch_delete(...)`
- `_delete_reconciliation_task_after_business_batch_delete(...)`

The cluster coordinates:

- `EtcReconciliationTaskService` version checks, task deletion, imported-invoice unlinking and OA draft deleted recording;
- `EtcService` legacy import batch deletion, submission batch deletion, business batch lookup/delete/reset, invoice metadata release and missing submission link repair;
- `ImportProcessingService` canonical ETC invoice removal by import batch;
- existing-invoice relinking and affected-month calculation;
- submitted business-batch Workbench relation write precondition and relation cancellation;
- derived lifecycle refresh through `_refresh_after_etc_invoice_link(...)`;
- state persistence after side effects.

## Why Not Move Directly Into Route Owner

The route owner should not own this cluster. It is not URL dispatch or HTTP parsing. It has business side effects, relation write preconditions, persistence, and read-model fan-out. Moving it into `routes_etc_reconciliation.py` would make the route owner a service and reintroduce mixed responsibilities.

## Why Not Move Whole Task Delete At Once

The full task-delete endpoint also owns HTTP body parsing, structured error mapping, and final response payload shape. Moving all of it at once would combine:

- API contract movement;
- cleanup service extraction;
- Workbench relation side-effect port design;
- persistence/refresh sequencing;
- task-delete idempotency/version behavior.

That is too broad for the next local slice.

## Selected Next Boundary

`server-py:etc-reconciliation-import-cleanup-service-extraction`

Extract the shared cleanup cluster into a service, expected name:

- `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py::EtcReconciliationImportCleanupService`

First-slice service methods should be scoped to cleanup behavior, not HTTP:

- `remove_imported_invoices(task, expected_version, actor) -> cleanup result`
- `delete_task_import_sources(task, actor) -> cleanup result` or equivalent
- optional helpers for business-batch lookup, unsubmitted submission batch cleanup, import batch source cleanup, and task cleanup after business batch delete if moving them together is still small enough.

The service should receive explicit dependencies/callbacks:

- `etc_service`;
- `import_service`;
- `reconciliation_task_service`;
- existing ETC invoice lookup callback;
- changed-month resolver callback;
- existing-invoice link callback;
- relation write precondition callback for submitted business batches;
- summary relation cancellation callback;
- persistence/refresh should remain in the HTTP/app layer for the first slice unless a return-object contract makes it clearly safe.

The route owner should continue to call app-level HTTP callbacks until the cleanup service is in place and tested.

## Guard/Test Requirements For Next Slice

Applicable tests:

- `tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_allows_reimport`
- `tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_deletes_unsubmitted_oa_draft`
- `tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_repairs_missing_unsubmitted_oa_draft_link`
- `tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_cancels_submitted_business_summary_relation`
- `tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_removes_orphan_submission_metadata_link`
- `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_summary_relation_delete_uses_workbench_relation_command_boundary`
- new or extended static guard proving import cleanup logic is not re-owned by `server.py` once extracted.

## Seven Test Categories

This audit changed no runtime behavior, so no tests were added.

For the next implementation slice:

1. Business core unit tests: applicable for task version, submitted-link conflict and imported-invoice cleanup state transitions.
2. Service-layer tests: required; cleanup service must cover `EtcService`, task service, import service and relation side-effect callbacks.
3. API contract tests: required through existing endpoint tests to prove response shape/status unchanged.
4. Read model/cache/background job tests: applicable if refresh/persistence sequencing changes; first slice should return changed months and keep refresh in app layer.
5. Frontend component/interaction tests: not directly applicable if API shape is unchanged.
6. End-to-end business-flow integration tests: applicable through targeted ETC backend integration tests for reimport/delete/reset recovery.
7. Existing feature regression tests: required for business-batch delete, submitted summary relation cancellation and orphan submission metadata cleanup.

## Next Prompt

Implement `server-py:etc-reconciliation-import-cleanup-service-extraction`.

Start by reading this audit, the server cleanup helpers, `EtcService`, `EtcReconciliationTaskService`, `tests/test_etc_backend.py` cleanup/delete tests, and platform boundary guards. Extract cleanup logic into a service with explicit dependencies. Keep HTTP response/error mapping in `Application` for the first slice. Add service tests or boundary guard coverage as needed, and rerun targeted ETC cleanup/delete API tests plus platform guards.
