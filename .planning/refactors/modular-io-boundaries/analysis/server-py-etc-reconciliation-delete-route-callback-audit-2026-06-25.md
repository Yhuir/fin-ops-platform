# server.py ETC reconciliation delete route callback audit

- Date: 2026-06-25
- Boundary: `server-py:etc-reconciliation-delete-route-callback-audit`
- Status: `local-implementation-closed`
- Module closure: `implementation-gap-open`
- Production: not used

## Result

Audited the remaining `/api/etc/reconciliation-tasks*` delete callbacks after `EtcReconciliationImportCleanupService` extraction and completed the safe local implementation slice immediately.

Moved these HTTP handlers from `Application` into `EtcReconciliationTaskApiRoutes`:

- `DELETE /api/etc/reconciliation-tasks/{task_id}/imported-invoices`
- `DELETE /api/etc/reconciliation-tasks/{task_id}`

Removed the app-owned callback methods:

- `_handle_api_etc_reconciliation_imported_invoices_delete`
- `_handle_api_etc_reconciliation_task_delete`

## Boundary Decision

The audit found that the remaining handler ownership was HTTP/write sequencing, not business cleanup ownership:

- JSON parsing and response/error mapping are already route-owner responsibilities.
- Import/submission/business-batch cleanup behavior is owned by `EtcReconciliationImportCleanupService`.
- Task state mutation remains in `EtcReconciliationTaskService`.
- Changed-month refresh and persistence are still platform side effects, so the route owner receives explicit callbacks instead of receiving `Application`.

The route owner now receives explicit dependencies:

- `cleanup_service`
- `expected_version_from_payload`
- `reconciliation_error_response`
- `refresh_after_etc_invoice_link`
- `persist_state`

It still does not receive `Application`, cookies, headers, auth/session objects or HTTP server objects.

## Why No Operation-Result Boundary First

A separate operation-result boundary is still useful for later broad cleanup, but it was not required for this narrow slice:

- The cleanup service already returns structured results containing updated task, delete result, canonical deletion count and changed months.
- The two migrated endpoints need only preserve existing response shape and refresh/persist sequencing.
- The route owner can hold HTTP response mapping without becoming a business service.

Refresh/persist callbacks remain a known residual platform port; they should be revisited if more ETC write routes are migrated or if derived lifecycle refresh needs a common operation-result wrapper.

## Tests Added Or Changed

Changed:

- `tests/test_platform_runtime_boundary_guards.py`
  - `test_etc_reconciliation_task_routes_delegate_to_route_owner` now asserts the route owner receives explicit cleanup/expected-version/persist ports.
  - The guard fails if `server.py` reintroduces either delete callback.
  - The guard checks that route-owner delete methods use the cleanup service and preserve refresh reasons.

Existing tests rerun:

- Targeted ETC imported-invoice removal regressions.
- Targeted ETC reconciliation task delete regressions.
- Targeted route-owner static guard.

## Seven Test Categories

1. Business core unit tests: covered by existing task delete/imported-invoice API regressions for version conflict, submitted-link conflict, cleanup and reimport state transitions.
2. Service-layer tests: covered indirectly by the existing cleanup service test from Row313; this slice did not change cleanup service behavior.
3. API contract tests: covered by targeted endpoint regressions for response status and key response fields.
4. Read model/cache/background job tests: not directly changed; targeted API regressions still exercise changed-month refresh side effects.
5. Frontend component and interaction tests: not applicable; frontend behavior and API shape are unchanged.
6. End-to-end business-flow integration tests: covered at backend integration level by imported-invoice remove/reimport and task delete cleanup regressions.
7. Existing feature regression tests: covered by summary relation cancellation and orphan submission metadata cleanup regressions.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_reconciliation.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_allows_reimport tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_deletes_unsubmitted_oa_draft tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_repairs_missing_unsubmitted_oa_draft_link tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_cancels_submitted_business_summary_relation tests.test_etc_backend.EtcApiTests.test_reconciliation_task_delete_removes_orphan_submission_metadata_link -v
```

Additional verification is required before commit:

```bash
bash scripts/verify.sh docs
git diff --check
git diff --cached --check
```

## Docs Impact

Updated `docs/modules/etc-tickets/implementation-notes.md` because route ownership changed.

Long-term product/API docs are unchanged: route paths, payload shape, permissions, business states and user-facing behavior did not change.

## Remaining Risk

Local implementation gaps remain:

- `/api/etc/import/*` still lives in `Application`.
- legacy `/api/etc/batches*` still lives in `Application`.
- refresh/persist sequencing is still callback-based, not yet a shared operation-result port.
- production browser/admin/write evidence remains final validation only.

## Next Boundary

`server-py:etc-import-route-owner-audit`

Audit `/api/etc/import/*` preview/confirm/direct import ownership and decide whether a route owner can be extracted with existing import session/job services, or whether job enqueue/readiness/result ports must be extracted first.
