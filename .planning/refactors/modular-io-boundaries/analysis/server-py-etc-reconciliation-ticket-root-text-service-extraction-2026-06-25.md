# server-py:etc-reconciliation-ticket-root-text-service-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Goal

Move ticket-root text source-file persistence, source naming, clipboard parser dispatch and parse-result application out of `Application`.

## Implementation

- Extended `EtcReconciliationSourceUploadService` with `submit_ticket_root_texts(...)`.
- The service now owns:
  - task lookup and expected-version check;
  - ticket-root source-mode conflict checks;
  - ticket-root manual text source naming;
  - source-file persistence;
  - `TicketRootClipboardTextParser().parse_text(...)` dispatch;
  - parse-result application.
- `Application._handle_api_etc_reconciliation_ticket_root_texts(...)` now only owns JSON body loading, `entries` shape validation, per-entry HTTP 400 mapping, actor fallback, service invocation and HTTP error mapping.
- `Application` no longer imports `TicketRootClipboardTextParser` or ticket-root source helper functions.

## Boundary Evidence

- Static Guard requires `Application._handle_api_etc_reconciliation_ticket_root_texts(...)` to delegate to `EtcReconciliationSourceUploadService.submit_ticket_root_texts(...)`.
- Static Guard forbids `TicketRootClipboardTextParser`, `store_uploaded_source_file(...)` and `apply_parse_result(...)` from returning to the ticket-root text callback.
- `EtcReconciliationSourceUploadService` still receives only explicit `task_service`; it does not receive `Application`.

## Tests

Added/updated:

- `tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_source_upload_service_submits_ticket_root_manual_text`
- `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner`

Re-run targeted API regressions:

- `test_ticket_root_text_route_creates_source_file_parse_result_and_items`
- `test_ticket_root_text_route_rejects_existing_pdf_ticket_root_source`
- `test_ticket_root_text_route_rejects_existing_txt_ticket_root_source`
- `test_ticket_root_text_route_returns_structured_storage_error`

## Seven Test Categories

- Business core unit tests: not directly changed; ticket-root parsing rules are unchanged.
- Service-layer tests: covered by the new direct service test for manual ticket-root text submission.
- API contract tests: covered by targeted ticket-root text route regressions.
- Read model/cache/background job tests: not applicable; no read model, cache, queue or worker behavior changed.
- Frontend component tests: not applicable; route and payload contract are unchanged.
- End-to-end business-flow integration tests: covered at backend API-flow level for text -> source file -> parse -> payload. Browser evidence remains final production validation.
- Existing feature regression tests: covered for source naming, source-mode conflict and storage-error behavior.

## Verification

Passed:

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py tests/test_etc_reconciliation_service.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_source_upload_service_submits_ticket_root_manual_text -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_creates_source_file_parse_result_and_items tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_rejects_existing_pdf_ticket_root_source tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_rejects_existing_txt_ticket_root_source tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_returns_structured_storage_error -v`
  - `test_ticket_root_text_route_rejects_existing_txt_ticket_root_source` skipped because its local real ticket-root sample file is absent.

Pending after state update:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check`

## Remaining Risk

The remaining `Application` upload/text callbacks are now thin HTTP wrappers. The next safe boundary is to collapse those wrappers into `EtcReconciliationTaskApiRoutes`, using the already-injected body parser/error mapper/source upload service ports.

## Next Boundary

`server-py:etc-reconciliation-upload-route-callback-collapse`
