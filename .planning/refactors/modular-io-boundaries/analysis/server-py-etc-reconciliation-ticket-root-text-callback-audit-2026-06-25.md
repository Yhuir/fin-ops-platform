# server-py:etc-reconciliation-ticket-root-text-callback-audit

Date: 2026-06-25
Status: analysis-closed

## Goal

Audit the remaining ETC reconciliation ticket-root text submission callback before moving it out of `Application`.

Target callback:

- `Application._handle_api_etc_reconciliation_ticket_root_texts(...)`

Route:

- `POST /api/etc/reconciliation-tasks/{task_id}/ticket-root-texts`

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-source-upload-service-extraction-2026-06-25.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph was used before the audit to inspect the current source upload service, `store_uploaded_source_file(...)`, parser dispatch and route delegation context.

## Findings

After Row328, the remaining ticket-root text callback is still broader than a thin HTTP wrapper. It owns:

- JSON body parsing and `entries` shape checks.
- Task lookup, expected-version check and source-mode conflict checks.
- Actor fallback.
- Per-entry object validation and blank text validation.
- Ticket-root clipboard source name generation.
- Source file persistence through `EtcReconciliationTaskService.store_uploaded_source_file(...)`.
- `TicketRootClipboardTextParser().parse_text(...)` dispatch.
- Parse-result application through `EtcReconciliationTaskService.apply_parse_result(...)`.
- Object-storage and validation error mapping.

The source-mode helper functions and source-name helper already moved into `EtcReconciliationSourceUploadService` in Row328, so ticket-root text submission should reuse that service boundary rather than creating another parallel service.

## Decision

Select the next implementation boundary:

`server-py:etc-reconciliation-ticket-root-text-service-extraction`

Scope for the next slice:

- Extend `EtcReconciliationSourceUploadService` with a method for ticket-root clipboard/manual text submissions.
- Move expected-version/source-mode conflict checks, source-name generation, source-file persistence, clipboard parser dispatch and parse-result application out of `Application`.
- Keep JSON body parsing and simple malformed-entry HTTP 400 response mapping in `Application` or route owner unless a smaller service input DTO is clearer.
- Keep `EtcReconciliationTaskApiRoutes` as URL dispatch only for this slice.
- Preserve source naming, error codes/messages, storage-error response shape and task payload shape.

## Required Regression Surface

The next implementation slice must include targeted coverage for:

- ticket-root text creates source file, parse result and ticket-root items;
- existing PDF source rejects text submission with current message;
- existing TXT file source rejects text submission with current message when local sample exists;
- storage error returns structured 503 and leaves no source files;
- static Guard proving ticket-root text parser/storage orchestration no longer lives in `Application`.

## Seven Test Categories

- Business core unit tests: not changed in this analysis slice.
- Service-layer tests: applies to the next implementation boundary because source-file persistence and parser dispatch will move to service.
- API contract tests: applies through existing ticket-root text route regressions.
- Read model/cache/background job tests: not applicable; no read model, cache, queue or worker behavior is involved.
- Frontend component tests: not applicable; route path and response shape are unchanged.
- End-to-end business-flow integration tests: backend API-flow tests are enough for this local slice; browser evidence remains final validation.
- Existing feature regression tests: applies for source-mode conflict messages, source naming and storage-error behavior.

## Verification

Analysis-only slice. No runtime code changed.

## Next Boundary

`server-py:etc-reconciliation-ticket-root-text-service-extraction`
