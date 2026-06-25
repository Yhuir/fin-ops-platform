# server.py ETC reconciliation import cleanup service extraction

- Date: 2026-06-25
- Boundary: `server-py:etc-reconciliation-import-cleanup-service-extraction`
- Status: `local-implementation-closed`
- Module closure: `implementation-gap-open`
- Production: not used

## Result

Extracted the shared ETC reconciliation import/submission/business-batch cleanup cluster from `Application` into an explicit service:

- `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py::EtcReconciliationImportCleanupService`

The service owns cleanup behavior for:

- imported-invoice removal from a reconciliation task;
- task import-source cleanup before task delete;
- unsubmitted OA/submission batch cleanup;
- task-linked business-batch import cleanup;
- import-batch metadata/canonical invoice cleanup;
- clearing task import state after legacy batch delete;
- deleting a local reconciliation task after business batch delete.

`Application` now keeps HTTP body parsing, response/error mapping, refresh-after-write and persistence sequencing, but no longer owns the cleanup helper implementation.

## Runtime Changes

- Added cleanup service result dataclasses:
  - `EtcImportedInvoicesRemovalResult`
  - `EtcTaskImportCleanupResult`
  - `EtcImportBatchCleanupResult`
  - `EtcSubmissionBatchCleanupResult`
- Added `Application._etc_reconciliation_import_cleanup_service()` as dependency assembly only.
- Replaced app-owned helper calls in:
  - `_handle_api_etc_reconciliation_imported_invoices_delete(...)`
  - `_handle_api_etc_reconciliation_task_delete(...)`
  - ETC business-batch delete/reset path
  - legacy `/api/etc/batches/{batch_id}` delete path
- Removed app-owned cleanup helper methods:
  - `_remove_reconciliation_task_imported_invoices`
  - `_delete_reconciliation_task_unsubmitted_submission_batch`
  - `_delete_reconciliation_task_import_batch_sources`
  - `_reconciliation_task_business_batch_for_import`
  - `_delete_reconciliation_task_business_batch_sources`
  - `_delete_etc_import_batch_sources`
  - `_clear_reconciliation_task_import_after_batch_delete`
  - `_delete_reconciliation_task_after_business_batch_delete`

## Boundary Decision

The service receives explicit dependencies/callbacks:

- `etc_service`
- `import_service`
- `reconciliation_task_service`
- existing ETC invoice lookup callback
- changed-month resolver callback
- existing-invoice link callback
- import-batch lookup callback
- submitted summary relation write-precondition callback
- submitted summary relation cancellation callback

The service does not receive `Application`, HTTP objects, route objects, cookies, headers, or auth/session state.

Refresh and persistence remain in `Application` for this slice because they are still HTTP/write-response sequencing decisions. Moving them requires a separate operation-result contract.

## Tests Added Or Changed

Added:

- `tests/test_etc_reconciliation_import_cleanup_service.py`
  - `test_submitted_business_batch_cleanup_requires_relation_preflight_before_delete`

Changed:

- `tests/test_platform_runtime_boundary_guards.py`
  - Existing ETC summary relation delete guard now checks the cleanup service owns task-linked business-batch cleanup and that `server.py` does not reintroduce that ownership.

Existing tests rerun:

- Targeted ETC imported-invoice/task delete API regressions.
- Targeted ETC route/summary relation boundary guards.

## Seven Test Categories

1. Business core unit tests: covered by existing ETC API regressions for version conflict, submitted-link conflict, task cleanup and reimport state transitions.
2. Service-layer tests: covered by the new direct cleanup service test proving submitted business-batch cleanup still uses relation preflight before delete.
3. API contract tests: covered by targeted endpoint regressions for imported-invoice removal and task delete.
4. Read model/cache/background job tests: partially covered by API regressions that exercise changed-month refresh behavior; no worker/background job behavior was changed.
5. Frontend component and interaction tests: not applicable; API shape and frontend behavior are unchanged.
6. End-to-end business-flow integration tests: covered at backend integration level by reimport/delete/reset recovery tests.
7. Existing feature regression tests: covered by business-batch summary relation cancellation and orphan submission metadata cleanup regressions.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_reconciliation_import_cleanup_service tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_summary_relation_delete_uses_workbench_relation_command_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_allows_reimport tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_deletes_unsubmitted_oa_draft tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_repairs_missing_unsubmitted_oa_draft_link tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_cancels_submitted_business_summary_relation tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_removes_orphan_submission_metadata_link -v
bash scripts/verify.sh docs
git diff --check
```

Initial failed check:

- The new direct service test first used `status="submitted"`, which does not match `ETC_BUSINESS_BATCH_SUBMITTED_STATUSES`; corrected the fake to `status="oa_submitted"` and reran successfully.

## Docs Impact

Updated `docs/modules/etc-tickets/implementation-notes.md` because internal service ownership changed.

Long-term product/API docs are unchanged: API paths, payload shape, state machine, permissions, and business semantics did not change.

## Remaining Risk

Local implementation gaps remain:

- `EtcReconciliationTaskApiRoutes` still delegates delete/imported-invoice HTTP handlers back to `Application`;
- `/api/etc/import/*` still lives in `Application`;
- legacy `/api/etc/batches*` still lives in `Application`;
- refresh/persistence sequencing remains app-owned and needs a separate operation-result boundary before moving;
- production browser/admin/write evidence remains final validation only.

## Next Boundary

`server-py:etc-reconciliation-delete-route-callback-audit`

Audit whether task delete and imported-invoice delete HTTP callbacks can now move into `EtcReconciliationTaskApiRoutes` using the cleanup service plus explicit refresh/persist/error mapping dependencies, or whether refresh/persistence needs an operation-result port first.
