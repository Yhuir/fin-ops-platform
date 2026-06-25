# Next Prompt

Continue after `server-py:etc-reconciliation-simple-mutation-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-simple-mutation-callback-collapse`.
- Row324 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-simple-mutation-callback-collapse-2026-06-25.md`.
- Row324 moved source-file delete, item patch, confirm, reopen and refresh-match HTTP mapping into `EtcReconciliationTaskApiRoutes`.
- Upload/parser-heavy reconciliation callbacks remain in `Application` by design:
  - `_handle_api_etc_reconciliation_upload`
  - `_handle_api_etc_reconciliation_supplement_for_card_upload`
  - `_handle_api_etc_reconciliation_ticket_root_texts`
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-upload-parser-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-simple-mutation-callback-collapse-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` `_etc_reconciliation_routes(...)` and remaining upload/parser callbacks
   - `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
   - `backend/src/fin_ops_platform/services/etc_document_parsers.py`
   - targeted ETC upload/parser tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph to inspect callers/callees for:
   - `_handle_api_etc_reconciliation_upload`
   - `_handle_api_etc_reconciliation_supplement_for_card_upload`
   - `_handle_api_etc_reconciliation_ticket_root_texts`
   - parser helpers and ticket-root source-mode helpers used by those callbacks.
4. Decide the next safe boundary:
   - route-owner migration for a narrow upload subset;
   - upload/parser application-service extraction;
   - object-storage/parser/source-mode helper extraction first;
   - or analysis-only if the coupling requires a smaller preparatory slice.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not mix all upload/parser flows into one broad implementation if the audit finds separate ownership concerns.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owners or services.
- Preserve object-storage error mapping and ticket-root source-mode conflict behavior.
- Keep read model refresh through existing explicit freshness/enqueue boundaries.
