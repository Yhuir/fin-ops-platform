# server.py ETC import route owner audit

- Date: 2026-06-25
- Boundary: `server-py:etc-import-route-owner-audit`
- Status: `local-implementation-closed`
- Module closure: `implementation-gap-open`
- Production: not used

## Result

Audited `/api/etc/import/*` ownership and completed the safe local implementation slice immediately.

Added:

- `backend/src/fin_ops_platform/app/routes_etc_import.py::EtcImportApiRoutes`

Moved these HTTP routes from `Application` into the route owner:

- `POST /api/etc/import`
- `POST /api/etc/import/preview`
- `POST /api/etc/import/confirm`

Removed app-owned handlers and helper:

- `_handle_api_etc_import`
- `_handle_api_etc_import_preview`
- `_handle_api_etc_import_confirm`
- `_etc_import_preview_items_with_filter_status`

The filter-status label helper moved with the route owner because it is presentation/HTTP payload decoration for preview output.

## Boundary Decision

The audit found the import endpoints could be route-owned without first extracting another service:

- Preview is HTTP multipart parsing, task-aware ZIP filtering, import preview payload decoration and session preview storage.
- Confirm is HTTP JSON parsing, idempotent background job creation, task import start, optional queue enqueue and response mapping.
- Import execution and read-model/derived lifecycle side effects already remain behind `ImportProcessingService` via `_execute_etc_invoice_import_confirm_job`.
- Queue enqueue remains behind an explicit injected port rather than direct repository/runtime access.

`EtcImportApiRoutes` receives explicit dependencies:

- `etc_service`
- `task_service`
- `background_job_service`
- `reconciliation_import_previews`
- JSON/multipart/body/response helpers
- reconciliation error mapper
- background job owner resolver
- import job processing flag
- import enqueue port
- import job serializer
- ETC import confirm execution port

It does not receive `Application`, auth/session objects, HTTP server objects, repositories or SQL access.

## Tests Added Or Changed

Changed:

- `tests/test_platform_runtime_boundary_guards.py`
  - Added `test_etc_import_routes_delegate_to_route_owner`.
  - The guard checks route owner construction, explicit dependencies, no whole-`Application` injection, no old app-owned import handlers, import route dispatch branches, task-aware preview filtering, idempotent background job creation and task import start.

Existing tests rerun:

- Targeted ETC task-aware import preview/confirm regressions.
- Targeted direct import removal regression.
- Targeted route-owner static guards.

## Seven Test Categories

1. Business core unit tests: covered by existing task-aware import regressions for task filtering, ready-state requirements, empty allowlist and confirmed item hash behavior.
2. Service-layer tests: not directly changed; import execution still goes through existing `ImportProcessingService`.
3. API contract tests: covered by targeted preview/confirm/direct import endpoint regressions and static route-owner guard.
4. Read model/cache/background job tests: covered by confirm tests that create/reuse background jobs and wait for successful job completion; no queue worker implementation changed.
5. Frontend component and interaction tests: not applicable; API shape and frontend behavior are unchanged.
6. End-to-end business-flow integration tests: covered at backend integration level by preview -> confirm -> background job -> task/invoice assertions.
7. Existing feature regression tests: covered by non-zip validation, direct import removal and no independent legacy batch list item regressions.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_import.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_import_routes_delegate_to_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_task_aware_etc_import_requires_task_filters_extra_and_marks_imported tests.test_etc_backend.EtcApiTests.test_task_aware_etc_import_does_not_create_independent_batch_list_item tests.test_etc_backend.EtcApiTests.test_task_aware_etc_import_confirm_imports_sum_matched_invoices_only tests.test_etc_backend.EtcApiTests.test_etc_import_preview_requires_ready_task_even_when_no_tasks_exist tests.test_etc_backend.EtcApiTests.test_task_aware_etc_import_preview_ignores_corrupt_zip_during_allowlist_filtering tests.test_etc_backend.EtcApiTests.test_task_aware_etc_import_empty_allowlist_does_not_import_original_zip tests.test_etc_backend.EtcApiTests.test_preview_rejects_non_zip_upload tests.test_etc_backend.EtcApiTests.test_old_direct_import_no_longer_persists_records -v
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

- legacy `/api/etc/batches*` still lives in `Application`.
- ETC invoice list/revoke-submitted routes still live in `Application`.
- `server.py` still owns many non-ETC module-specific route/helper surfaces.
- production browser/admin/write evidence remains final validation only.

## Next Boundary

`server-py:etc-legacy-batch-route-owner-audit`

Audit legacy `/api/etc/batches*` compatibility route ownership and decide whether it should move to a compat-only route owner, be partially delegated to existing `EtcBusinessBatchApiRoutes`, or require another side-effect service boundary first.
