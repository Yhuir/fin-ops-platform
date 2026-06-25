# server-py:etc-reconciliation-source-upload-service-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Goal

Move generic ETC reconciliation source upload store+parse+apply orchestration and ticket-root source-mode policy out of `Application`.

## Scope

Routes still enter through `EtcReconciliationTaskApiRoutes` and the existing thin `Application._handle_api_etc_reconciliation_upload(...)` wrapper:

- `POST /api/etc/reconciliation-tasks/{task_id}/credit-card-statement`
- `POST /api/etc/reconciliation-tasks/{task_id}/ticket-root-files`
- `POST /api/etc/reconciliation-tasks/{task_id}/supplement-evidences`

This slice did not move ticket-root text submission.

## Implementation

- Added `EtcReconciliationSourceUploadService`.
- Added `EtcReconciliationSourceUpload` as the app-independent upload input DTO.
- Added `EtcReconciliationWrongSourceSlotError` so the HTTP wrapper can preserve the existing `wrong_reconciliation_source_kind` response shape.
- Moved the following out of `server.py`:
  - credit-card/ticket-root/supplement parser dispatch;
  - source-file store + parse-result apply loop;
  - ticket-root wrong-slot detection;
  - ticket-root TXT/PDF/manual-paste mode conflict policy;
  - ticket-root TXT encoding/content-type selection;
  - ticket-root TXT file blocking parse issue helper;
  - ticket-root source classification helpers used by the remaining text route.
- `Application._handle_api_etc_reconciliation_upload(...)` now only handles multipart loading, empty file HTTP error, expected-version extraction, service invocation and HTTP error mapping.
- `Application._handle_api_etc_reconciliation_ticket_root_texts(...)` now imports ticket-root source classifiers and source-name helper from the new service module.

## Boundary Evidence

- `server.py` no longer imports `CcbCreditCardStatementParser`, `TicketRootDocumentParser`, `SupplementEvidenceParser` or `etc_document_parsers`.
- Static Guard requires `Application._handle_api_etc_reconciliation_upload(...)` to delegate to `EtcReconciliationSourceUploadService.upload_sources(...)`.
- Static Guard forbids parser/source-mode helper details from returning to `server.py`.
- The new service receives explicit `task_service`; it does not receive `Application`.

## Tests

Added/updated:

- `tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_source_upload_service_imports_ticket_root_text_file`
- `tests.test_etc_backend.EtcApiTests.test_reconciliation_task_level_supplement_upload_parses_evidence`
- `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner`

Re-run targeted API regressions:

- ticket-root TXT clipboard parser path;
- ticket-root GB18030 TXT path;
- ticket-root storage error path;
- credit-card wrong-slot diagnostics including PDF-extracted text;
- credit-card statement storage error path;
- ticket-root existing clipboard conflict path;
- Chinese CCB wrong-slot diagnostics.

## Seven Test Categories

- Business core unit tests: not directly changed; parser and reconciliation business rules were moved behind a service boundary without changing rules.
- Service-layer tests: covered by the direct source upload service TXT import test.
- API contract tests: covered by targeted `Application.handle_request(...)` upload regressions and the new task-level supplement upload regression.
- Read model/cache/background job tests: not applicable; no read model, cache, queue or worker behavior changed.
- Frontend component tests: not applicable; route paths and response shapes are unchanged.
- End-to-end business-flow integration tests: covered at backend API-flow level for upload -> store -> parse -> task payload. Browser evidence remains final production validation.
- Existing feature regression tests: covered for ticket-root source-mode/wrong-slot/storage behavior and credit-card/supplement upload paths.

## Verification

Passed:

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_etc_reconciliation.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py tests/test_etc_reconciliation_service.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_source_upload_service_imports_ticket_root_text_file -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_txt_file_with_clipboard_parser tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_gb18030_txt_file_with_clipboard_parser tests.test_etc_backend.EtcApiTests.test_ticket_root_txt_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_credit_card_statement_uploaded_to_ticket_root_route_returns_wrong_slot_message tests.test_etc_backend.EtcApiTests.test_credit_card_pdf_uploaded_to_ticket_root_route_uses_extracted_text_for_wrong_slot_detection tests.test_etc_backend.EtcApiTests.test_credit_card_statement_upload_returns_structured_storage_error -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_rejects_existing_clipboard_text_source tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_rejects_existing_txt_ticket_root_source_before_pdf_upload tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_rejects_existing_pdf_ticket_root_source_before_txt_upload tests.test_etc_backend.EtcApiTests.test_chinese_ccb_statement_uploaded_to_ticket_root_route_returns_wrong_slot_message -v`
  - Two tests skipped because their local real ticket-root sample file is absent.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_reconciliation_task_level_supplement_upload_parses_evidence -v`
- Combined targeted regression command with 11 tests passed.

Pending after state update:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check`

## Remaining Risk

`Application._handle_api_etc_reconciliation_ticket_root_texts(...)` still owns JSON validation, source-file persistence, clipboard parser dispatch and storage/error mapping. It should be audited next as a separate source-mode/text submission boundary.

## Next Boundary

`server-py:etc-reconciliation-ticket-root-text-callback-audit`
