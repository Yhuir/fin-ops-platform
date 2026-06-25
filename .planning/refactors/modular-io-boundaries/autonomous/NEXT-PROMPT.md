# Next Prompt

Continue after `server-py:input-invoice-usage-oa-reverse-route-owner-facade-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-oa-reverse-route-owner-facade-extraction`.
- Row344 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-route-owner-facade-extraction-2026-06-25.md`.
- `InputInvoiceUsageOaReverseApiRoutes` now owns lightweight OA reverse HTTP mapping for:
  - preview;
  - submitted history;
  - staged drafts;
  - batch create;
  - batch get.
- `server.py` still owns the remaining OA reverse mutation callbacks:
  - one-step draft create;
  - batch draft create;
  - batch draft revoke;
  - status refresh;
  - manual OA status.
- Rows/filter-options/export/read-model routes remain out of this boundary.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:input-invoice-usage-oa-reverse-draft-mutation-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-route-owner-facade-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-route-owner-audit-2026-06-25.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/input-invoice-usage/tests.md`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_input_invoice_usage_oa_reverse_one_step_draft_create(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_draft_create(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_draft_revoke(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_status_refresh(...)`;
     - `_handle_api_input_invoice_usage_oa_reverse_manual_status(...)`;
     - `_input_invoice_usage_oa_draft_client_for_batch(...)`;
     - `_target_oa_applicant_token_provider(...)`;
     - `_input_invoice_usage_mutation_actor(...)`;
     - `_input_invoice_usage_oa_reverse_error_response(...)`.
   - `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before selecting or editing any implementation boundary.
4. Produce an analysis file for the remaining draft mutation callbacks:
   - identify which callback can be safely moved into `InputInvoiceUsageOaReverseApiRoutes` next;
   - identify whether any service/application-service extraction is required before callback collapse;
   - keep OA token/header parsing out of services;
   - preserve idempotency, expected version, relation command conflict, audit and read model invalidation behavior;
   - do not touch rows/filter-options/export/read-model fresh gates.
5. If the audit proves a narrow safe implementation boundary, execute it locally with tests and static Guard evidence; otherwise update state with the selected next implementation prompt.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change OA reverse response shape, status codes, permission behavior, idempotency, version conflict or read model invalidation.
- Do not move OA token/header parsing into business services.
- Do not pass the whole `Application` into route owner or services.
- Do not touch rows/filter-options/export/read-model fresh gates.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
