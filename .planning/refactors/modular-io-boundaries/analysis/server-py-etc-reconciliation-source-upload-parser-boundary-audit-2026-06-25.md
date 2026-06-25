# server-py:etc-reconciliation-source-upload-parser-boundary-audit

Date: 2026-06-25
Status: analysis-closed

## Goal

Audit the remaining generic ETC reconciliation source upload callback before moving it out of `Application`.

Target callback:

- `Application._handle_api_etc_reconciliation_upload(...)`

Routes using it through `EtcReconciliationTaskApiRoutes`:

- `POST /api/etc/reconciliation-tasks/{task_id}/credit-card-statement`
- `POST /api/etc/reconciliation-tasks/{task_id}/ticket-root-files`
- `POST /api/etc/reconciliation-tasks/{task_id}/supplement-evidences`

Ticket-root text submission is intentionally out of scope.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-supplement-for-card-upload-callback-collapse-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-upload-parser-callback-audit-2026-06-25.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/etc_document_parsers.py`
- `tests/test_etc_backend.py`
- `tests/test_etc_reconciliation_service.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph was used before the audit to inspect the ETC reconciliation task service and related symbols. The source upload callback itself is still an `Application` method and is best inspected directly with the current file after Row326.

## Findings

`_handle_api_etc_reconciliation_upload(...)` is not just HTTP mapping. It currently owns all of the following:

- Multipart field/file loading and empty-file HTTP error mapping.
- Actor and expected-version extraction.
- Task lookup and version/status validation.
- Ticket-root wrong-slot detection via `_reconciliation_wrong_slot_message(...)`.
- Ticket-root source-mode classification via `_ticket_root_upload_source_mode(...)`.
- TXT/PDF/manual paste conflict validation via `_validate_ticket_root_upload_source_mode(...)`.
- Content-type selection for ticket-root TXT uploads.
- Source file persistence through `EtcReconciliationTaskService.store_uploaded_source_file(...)`.
- Parser dispatch:
  - `CcbCreditCardStatementParser().parse_pdf_bytes(...)`
  - `TicketRootClipboardTextParser().parse_text(...)`
  - `_ticket_root_text_file_not_trip_result(...)`
  - `TicketRootDocumentParser().parse_file(...)`
  - `SupplementEvidenceParser().parse_text(...)`
- Parse-result application through `EtcReconciliationTaskService.apply_parse_result(...)`.
- Storage and validation error mapping.

These responsibilities are too broad to move directly into `EtcReconciliationTaskApiRoutes`: doing so would make the route owner a parser/source-mode application service instead of a HTTP mapping boundary.

## Route Classification

- Credit-card statement upload is comparatively simple but still stores a source file then dispatches a parser and applies the parse result.
- Task-level supplement evidence upload is similarly simple but still owns parser dispatch and evidence-kind override handling.
- Ticket-root file upload is the risky path: wrong-slot detection, text encoding, TXT/PDF source-mode classification, mixed-upload rejection and existing-source conflict behavior all need to stay together and be regression-protected.

## Decision

Select the next implementation boundary:

`server-py:etc-reconciliation-source-upload-service-extraction`

Scope for the next slice:

- Add an explicit service/facade boundary, tentatively `EtcReconciliationSourceUploadService`, that owns source upload store+parse+apply orchestration for the three generic source upload routes.
- Move ticket-root source-mode/wrong-slot/content-type/parser dispatch behavior out of `Application` into that service boundary or helper module owned by it.
- Keep `EtcReconciliationTaskApiRoutes` responsible only for URL dispatch and, at most, HTTP/multipart field extraction and response/error mapping.
- Keep ticket-root text submission out of this implementation slice unless the code shows an unavoidable helper ownership conflict.
- Preserve current error codes/messages, parser output shape, storage rollback behavior and expected-version/status behavior.

## Required Regression Surface

The next implementation slice must include targeted coverage for:

- Credit-card statement upload storage error and expected-version/status behavior.
- Ticket-root TXT upload using clipboard parser and not document parser.
- Ticket-root GB18030 TXT encoding/content-type behavior.
- Ticket-root wrong-slot detection for credit-card statement content and PDF-extracted text.
- Ticket-root source-mode conflicts for existing manual text, TXT and PDF/JPG sources.
- Task-level supplement evidence parser behavior if touched.
- Static Guard proving generic source upload parser orchestration no longer lives in `Application` after extraction.

## Seven Test Categories

- Business core unit tests: next slice should add service-level tests if parser/source-mode policy moves into a service.
- Service-layer tests: applies to the next implementation boundary because store+parse+apply orchestration will move out of `Application`.
- API contract tests: applies through targeted existing `Application.handle_request(...)` regressions.
- Read model/cache/background job tests: not applicable; no read model/worker behavior is involved.
- Frontend component tests: not applicable; route and payload contract should remain unchanged.
- End-to-end business-flow integration tests: targeted API route flows are enough for this slice; browser validation remains final production evidence.
- Existing feature regression tests: applies strongly for ticket-root mode conflicts and wrong-slot diagnostics.

## Verification

Analysis-only slice. No runtime code changed.

## Next Boundary

`server-py:etc-reconciliation-source-upload-service-extraction`
