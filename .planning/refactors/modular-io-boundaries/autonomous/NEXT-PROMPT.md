# Next Prompt

Continue after `server-py:etc-reconciliation-ticket-root-text-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-ticket-root-text-callback-audit`.
- Row329 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-ticket-root-text-callback-audit-2026-06-25.md`.
- Generic source upload orchestration now lives in `EtcReconciliationSourceUploadService`.
- Ticket-root text submission still lives in `Application._handle_api_etc_reconciliation_ticket_root_texts(...)`.
- Row329 selected extending `EtcReconciliationSourceUploadService` for ticket-root text source-file persistence, source naming, clipboard parser dispatch and parse-result application.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-ticket-root-text-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-ticket-root-text-callback-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` `_handle_api_etc_reconciliation_ticket_root_texts(...)`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
   - ticket-root text tests in `tests/test_etc_backend.py`
   - service tests in `tests/test_etc_reconciliation_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect ticket-root text callback and source upload service symbols.
4. Implement only ticket-root text service extraction:
   - extend `EtcReconciliationSourceUploadService`;
   - move expected-version/source-mode conflict checks, source-name generation, source-file persistence, clipboard parser dispatch and parse-result application out of `Application`;
   - keep malformed JSON/entry HTTP response mapping thin in `Application` unless a smaller DTO is clearer;
   - preserve error codes/messages and task payload shape.
5. Update service/API/static Guard tests.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not pass `Application` into the service.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Preserve ticket-root text response shape, source naming, source-mode conflict messages, storage error mapping and parser output shape.
