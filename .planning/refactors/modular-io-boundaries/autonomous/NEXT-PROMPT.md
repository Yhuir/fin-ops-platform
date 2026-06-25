# Next Prompt

Continue after `server-py:etc-reconciliation-upload-parser-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-upload-parser-callback-audit`.
- Row325 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-upload-parser-callback-audit-2026-06-25.md`.
- Row325 selected supplement-for-card upload callback collapse as the next narrow implementation boundary.
- Generic source upload and ticket-root text submission remain out of scope for Row326.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-supplement-for-card-upload-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-upload-parser-callback-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` `_etc_reconciliation_routes(...)` and `_handle_api_etc_reconciliation_supplement_for_card_upload(...)`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_service.py` `upload_supplement_evidences_for_card(...)`
   - targeted supplement upload tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph to inspect callers/callees for `_handle_api_etc_reconciliation_supplement_for_card_upload`, `upload_supplement_evidences_for_card`, and `EtcReconciliationTaskApiRoutes`.
4. Implement only supplement-for-card callback collapse:
   - move HTTP mapping into `EtcReconciliationTaskApiRoutes`;
   - inject `load_multipart_body` and storage-error response ports if required;
   - remove `_handle_api_etc_reconciliation_supplement_for_card_upload(...)` from `server.py`;
   - keep generic source upload and ticket-root text callbacks unchanged;
   - update Guard coverage and targeted regressions.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not move generic source upload or ticket-root text submission in this slice.
- Do not move parser/source-mode helper ownership in this slice.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owners or services.
- Preserve object-storage error mapping and supplement amount-delta note behavior.
