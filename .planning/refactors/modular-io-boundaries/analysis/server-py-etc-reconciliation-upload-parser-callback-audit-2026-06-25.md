# server-py:etc-reconciliation-upload-parser-callback-audit

## Status

`analysis-closed`

## Goal

Audit the remaining upload/parser-heavy ETC reconciliation callbacks still injected from `Application` and choose the next smallest safe implementation boundary.

## Evidence Reviewed

- `analysis/server-py-etc-reconciliation-simple-mutation-callback-collapse-2026-06-25.md`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/etc_document_parsers.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Findings

After Row324, `EtcReconciliationTaskApiRoutes` still receives three callbacks from `Application`:

- `upload_source=self._handle_api_etc_reconciliation_upload`
- `upload_supplement_for_card=self._handle_api_etc_reconciliation_supplement_for_card_upload`
- `submit_ticket_root_texts=self._handle_api_etc_reconciliation_ticket_root_texts`

These are not equivalent in risk:

1. `upload_supplement_for_card` is the smallest safe implementation boundary.
   - Route code parses multipart fields/files and expected version.
   - It converts uploads into file dictionaries and calls `EtcReconciliationTaskService.upload_supplement_evidences_for_card(...)`.
   - Business checks, duplicate detection, amount-delta note enforcement, storage rollback and parse-result application are already service-owned.
   - Moving this HTTP mapping into `EtcReconciliationTaskApiRoutes` does not require moving parser/source-mode helpers.

2. `upload_source` is broader.
   - It covers credit-card statements, ticket-root files and generic supplement evidence.
   - It owns ticket-root wrong-slot detection, TXT/PDF source-mode classification, content-type selection and parser dispatch.
   - It should not be mixed into the supplement-for-card slice.

3. `submit_ticket_root_texts` is also broader.
   - It owns JSON validation, source-mode conflict checks, source-file creation, source naming and ticket-root clipboard parser dispatch.
   - It should likely move with a ticket-root source-mode/parser service or a dedicated route-owner slice after helper ownership is clarified.

## Decision

Select:

`server-py:etc-reconciliation-supplement-for-card-upload-callback-collapse`

Scope:
- Move `_handle_api_etc_reconciliation_supplement_for_card_upload(...)` body into `EtcReconciliationTaskApiRoutes`.
- Inject `load_multipart_body` and storage-error-response ports as needed.
- Remove only the supplement-for-card callback from `server.py` and `_etc_reconciliation_routes(...)`.
- Keep `upload_source` and `submit_ticket_root_texts` callbacks unchanged.
- Add/update static Guard coverage and run targeted supplement upload regressions.

## Verification

Analysis-only slice. No runtime code changed.

## Next Boundary

`server-py:etc-reconciliation-supplement-for-card-upload-callback-collapse`
