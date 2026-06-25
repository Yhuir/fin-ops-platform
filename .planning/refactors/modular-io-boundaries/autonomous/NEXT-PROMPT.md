# Next Prompt

Continue after `server-py:etc-business-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-business-route-owner-local-closure-audit`.
- Row342 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-route-owner-local-closure-audit-2026-06-25.md`.
- ETC business-batch route-owner local support is accounted for:
  - `EtcBusinessBatchApiRoutes` owns active business-batch route mapping.
  - `EtcBusinessBatchApplicationService` owns payload workflows and link/refresh sequencing.
  - `EtcBusinessBatchDeleteService` owns delete side-effect orchestration.
  - Remaining `server.py` business-batch functions are dispatch/session/body/response wrappers, dependency assembly, or legacy compatibility resolver.
- Whole ETC/global closure is not claimed.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:input-invoice-usage-oa-reverse-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-route-owner-local-closure-audit-2026-06-25.md`
   - `docs/modules/README.md`
   - the input invoice usage module docs under `docs/modules/` if present;
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_input_invoice_usage_rows(...)`
     - `_handle_api_input_invoice_usage_filter_options(...)`
     - `_handle_api_input_invoice_usage_export_preview(...)`
     - `_handle_api_input_invoice_usage_export(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_preview(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_batch_create(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_submitted_history(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_staged_drafts(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_one_step_draft_create(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_batch_get(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_draft_create(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_draft_revoke(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_status_refresh(...)`
     - `_handle_api_input_invoice_usage_oa_reverse_manual_status(...)`
   - related `input_invoice_usage` service files and tests.
3. Use CodeGraph before selecting any implementation boundary.
4. Perform an audit-only boundary first:
   - classify the input-invoice usage OA reverse handler group;
   - identify existing service/application/route-owner abstractions to reuse;
   - select the smallest safe next implementation slice;
   - document tests, docs impact and stop gates.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change runtime behavior during the audit.
- Do not move OA token/header parsing into business services.
- Do not pass the whole `Application` into services.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
