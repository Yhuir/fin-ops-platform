# server-py:etc-reconciliation-upload-route-callback-collapse

Date: 2026-06-25
Status: local-implementation-closed

## Goal

Move the remaining thin ETC reconciliation upload/text HTTP callbacks out of `Application` and into `EtcReconciliationTaskApiRoutes`.

## Implementation

- `EtcReconciliationTaskApiRoutes` now receives `source_upload_service`.
- Moved generic source upload HTTP mapping into `EtcReconciliationTaskApiRoutes.upload_source(...)`.
- Moved ticket-root text HTTP mapping into `EtcReconciliationTaskApiRoutes.submit_ticket_root_texts(...)`.
- Removed from `server.py`:
  - `_handle_api_etc_reconciliation_upload(...)`
  - `_handle_api_etc_reconciliation_ticket_root_texts(...)`
- `server.py` now only assembles `EtcReconciliationTaskApiRoutes` dependencies and the source upload service.

## Boundary Evidence

- Static Guard requires `source_upload_service=self._etc_reconciliation_source_upload_service()` in route owner assembly.
- Static Guard requires route owner upload/text methods to delegate parser orchestration to `EtcReconciliationSourceUploadService`.
- Static Guard forbids the removed upload/text app callbacks from returning to `server.py`.
- Route owner still does not receive `Application`.

## Tests

Updated:

- `tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner`

Re-run targeted API regressions:

- ticket-root TXT upload;
- ticket-root GB18030 TXT upload;
- ticket-root TXT storage error;
- credit-card wrong-slot diagnostics;
- credit-card statement storage error;
- task-level supplement evidence upload;
- ticket-root text create;
- ticket-root text PDF-source conflict;
- ticket-root text storage error.

## Seven Test Categories

- Business core unit tests: not changed; business/parser logic already lives in services.
- Service-layer tests: existing Row328/Row330 direct service tests still cover moved orchestration.
- API contract tests: covered by targeted upload/text API regressions.
- Read model/cache/background job tests: not applicable; no read model, cache, queue or worker behavior changed.
- Frontend component tests: not applicable; route paths and response shapes are unchanged.
- End-to-end business-flow integration tests: covered at backend API-flow level for upload/text -> service -> task payload. Browser evidence remains final production validation.
- Existing feature regression tests: covered by source upload/text storage, parser and conflict regressions.

## Verification

Passed:

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_reconciliation.py backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py tests/test_etc_reconciliation_service.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_txt_file_with_clipboard_parser tests.test_etc_backend.EtcApiTests.test_ticket_root_upload_route_imports_gb18030_txt_file_with_clipboard_parser tests.test_etc_backend.EtcApiTests.test_ticket_root_txt_file_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_credit_card_statement_uploaded_to_ticket_root_route_returns_wrong_slot_message tests.test_etc_backend.EtcApiTests.test_credit_card_statement_upload_returns_structured_storage_error tests.test_etc_backend.EtcApiTests.test_reconciliation_task_level_supplement_upload_parses_evidence tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_creates_source_file_parse_result_and_items tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_rejects_existing_pdf_ticket_root_source tests.test_etc_backend.EtcApiTests.test_ticket_root_text_route_returns_structured_storage_error -v`

Pending after state update:

- `bash scripts/verify.sh docs`
- `git diff --check`
- `git diff --cached --check`

## Remaining Risk

ETC reconciliation task route ownership is now locally much thinner, but a local closure audit is still needed to confirm no residual app-owned reconciliation task route/helper responsibilities remain before moving to the next server-py area.

## Next Boundary

`server-py:etc-reconciliation-route-owner-local-closure-audit`
