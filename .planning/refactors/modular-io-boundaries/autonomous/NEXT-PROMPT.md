# Next Prompt

Continue after `server-py:input-invoice-usage-oa-reverse-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-oa-reverse-route-owner-audit`.
- Row343 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-route-owner-audit-2026-06-25.md`.
- `InputInvoiceUsageOaReverseService` owns OA reverse business state, idempotency, version conflict, draft/revoke/status/manual status, relation command write, audit and read model invalidation.
- `server.py` still owns route dispatch and HTTP/session/body/error mapping for `/api/input-invoice-usage/oa-reverse*`.
- The next implementation slice should move only lightweight OA reverse route mapping first:
  - preview;
  - submitted history;
  - staged drafts;
  - batch create;
  - batch get.
- Keep OA draft create/revoke/status refresh/manual status callbacks in `server.py` for a follow-up slice.
- Keep rows/filter-options/export/read-model routes out of this boundary.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:input-invoice-usage-oa-reverse-route-owner-facade-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-route-owner-audit-2026-06-25.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/input-invoice-usage/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - OA reverse dispatch in `_handle_request_untracked(...)`;
     - `_input_invoice_usage_oa_reverse_service(...)`;
     - `_input_invoice_usage_mutation_actor(...)`;
     - `_input_invoice_usage_oa_reverse_error_response(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_preview(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_batch_create(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_submitted_history(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_staged_drafts(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_batch_get(...)`.
   - `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing.
4. Implement the route-owner facade extraction:
   - add `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`;
   - define `InputInvoiceUsageOaReverseApiRoutes` with explicit ports, not `Application`;
   - route preview/history/staged/batch create/get through this owner;
   - keep draft create/revoke/status refresh/manual status in `server.py` for a later slice;
   - add or extend static Guard;
   - run targeted API regressions for the moved paths.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change OA reverse response shape, status codes, permission behavior, idempotency, version conflict or read model invalidation.
- Do not move OA token/header parsing into business services.
- Do not pass the whole `Application` into route owner or services.
- Do not touch rows/filter-options/export/read-model fresh gates.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
