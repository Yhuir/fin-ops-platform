# Next Prompt

Continue after `server-py:etc-reconciliation-source-upload-service-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-source-upload-service-extraction`.
- Row328 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-source-upload-service-extraction-2026-06-25.md`.
- Generic source upload store+parse+apply orchestration and ticket-root wrong-slot/source-mode/content-type policy now live in `EtcReconciliationSourceUploadService`.
- `Application._handle_api_etc_reconciliation_upload(...)` is a thin HTTP wrapper.
- Ticket-root text submission still lives in `Application._handle_api_etc_reconciliation_ticket_root_texts(...)`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-ticket-root-text-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-source-upload-service-extraction-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` `_handle_api_etc_reconciliation_ticket_root_texts(...)`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
   - ticket-root text tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect ticket-root text callback callers/callees, source-file persistence and parser dispatch.
4. Audit only ticket-root text submission ownership:
   - classify JSON validation, expected-version/status/source-mode conflict checks, source-file persistence, source naming and clipboard parser dispatch;
   - decide whether to extend `EtcReconciliationSourceUploadService` or create a separate text submission service;
   - do not change production/browser/admin/write validation.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into any service.
- Preserve ticket-root text response shape, source naming, source-mode conflict messages, storage error mapping and parser output shape.
