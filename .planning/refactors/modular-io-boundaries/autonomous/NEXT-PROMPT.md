# Next Prompt

Continue after `server-py:etc-reconciliation-supplement-for-card-upload-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-supplement-for-card-upload-callback-collapse`.
- Row326 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-supplement-for-card-upload-callback-collapse-2026-06-25.md`.
- Per-card supplement upload HTTP mapping now lives in `EtcReconciliationTaskApiRoutes`.
- `_handle_api_etc_reconciliation_supplement_for_card_upload(...)` has been removed from `server.py`.
- Generic source upload and ticket-root text submission remain out of scope for Row326 and still need separate parser/source-mode analysis.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-source-upload-parser-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-supplement-for-card-upload-callback-collapse-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-upload-parser-callback-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` `_handle_api_etc_reconciliation_upload(...)`
   - ticket-root source-mode helpers near `_handle_api_etc_reconciliation_upload(...)`
   - credit-card/ticket-root/task-level supplement source upload tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph to inspect callers/callees for `_handle_api_etc_reconciliation_upload`, `store_uploaded_source_file`, `apply_parse_result`, parser classes and `EtcReconciliationTaskApiRoutes`.
4. Audit only generic source upload parser/source-mode ownership:
   - classify credit-card statement, ticket-root file and task-level supplement evidence upload paths;
   - identify which parser/source-mode/wrong-slot/content-type logic belongs in service/facade versus route owner;
   - decide the next smallest implementation boundary;
   - do not move ticket-root text submission in this audit.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not move generic source upload code in the audit slice unless the boundary is proven smaller and safe.
- Do not move ticket-root text submission in this slice.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owners or services.
- Preserve object-storage error mapping, wrong-slot validation, ticket-root source-mode conflict behavior, parser output shape and supplement parse behavior.
