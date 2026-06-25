# server-py:etc-reconciliation-supplement-for-card-upload-callback-collapse

Date: 2026-06-25
Status: local-implementation-closed

## Goal

Move the per-credit-card supplement evidence upload HTTP mapping out of `Application` and into `EtcReconciliationTaskApiRoutes`, without touching the generic reconciliation source upload parser flow or ticket-root text submission flow.

## Scope

- Target route: `POST /api/etc/reconciliation-tasks/{task_id}/supplement-evidences/{item_id}`.
- Moved multipart parsing, expected-version parsing, actor/note/evidence-kind field extraction, storage error mapping and task payload response mapping into `EtcReconciliationTaskApiRoutes.upload_supplement_for_card(...)`.
- Removed `Application._handle_api_etc_reconciliation_supplement_for_card_upload(...)`.
- Kept generic source upload callback `_handle_api_etc_reconciliation_upload(...)` in `Application` because it still owns parser/source-mode/wrong-slot/content-type decisions.
- Kept ticket-root text callback `_handle_api_etc_reconciliation_ticket_root_texts(...)` in `Application` because it still owns parser/source-name entry validation.

## Inputs / Outputs / State

- Input: multipart fields and files from the existing request body parser port.
- Output: existing task payload response shape through the injected task payload port.
- State mutation: still owned by `EtcReconciliationTaskService.upload_supplement_evidences_for_card(...)`.
- Event/read-model impact: no new read-model, queue, dirty-scope, cache or worker behavior in this slice.
- Permission/session impact: unchanged; this route path did not gain a new auth/session owner in this slice.

## Boundary Evidence

- `server.py` now injects explicit ports into `EtcReconciliationTaskApiRoutes`: `load_multipart_body`, `expected_version_from_fields` and `reconciliation_storage_error_response`.
- Route owner does not receive the whole `Application`.
- The static guard now forbids `_handle_api_etc_reconciliation_supplement_for_card_upload` from returning to `server.py`.
- Upload/parser-heavy generic source upload and ticket-root text remain explicit callbacks and are documented stop gates for later slices.

## Tests

Added/updated:

- `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner`
  - Requires the new multipart/version/storage ports.
  - Forbids the removed supplement-for-card app callback.
- `tests.test_etc_backend.EtcApiTests.test_reconciliation_item_supplement_upload_returns_structured_storage_error`
  - Proves the migrated route still maps `ObjectStorageWriteError` to structured 503 and leaves no supplement evidence behind.

Re-run existing targeted regression:

- `tests.test_etc_backend.EtcApiTests.test_reconciliation_item_supplement_upload_requires_note_for_amount_delta`
  - Proves amount-delta note behavior and successful link payload remain unchanged.

## Seven Test Categories

- Business core unit tests: not changed; business rules remain in `EtcReconciliationTaskService` and existing service tests cover amount-delta behavior.
- Service-layer tests: existing service behavior is unchanged; no new service dependency or persistence path was introduced.
- API contract tests: covered by the supplement upload note/error API tests.
- Read model/cache/background job tests: not applicable; no read model, cache, queue or worker behavior changed.
- Frontend interaction tests: not applicable; HTTP response contract and route path are unchanged.
- End-to-end business-flow integration tests: covered narrowly by the API route flow through `Application.handle_request(...)`; broader browser flow remains final validation.
- Existing feature regression tests: covered by existing amount-delta upload regression and new storage-error regression.

## Verification

Passed:

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_reconciliation.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_reconciliation_item_supplement_upload_requires_note_for_amount_delta tests.test_etc_backend.EtcApiTests.test_reconciliation_item_supplement_upload_returns_structured_storage_error -v`

Pending after state update:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check`

## Remaining Risk

Generic source upload and ticket-root text submission still live as `Application` callbacks because they carry parser/source-mode responsibilities beyond this slice. The next safe boundary is an audit of generic source upload parser/source-mode ownership before moving any more code.

## Next Boundary

`server-py:etc-reconciliation-source-upload-parser-boundary-audit`
