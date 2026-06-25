# Next Prompt

Continue after `server-py:input-invoice-usage-oa-reverse-draft-mutation-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-oa-reverse-draft-mutation-route-callback-collapse`.
- Row346 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-draft-mutation-route-callback-collapse-2026-06-25.md`.
- `InputInvoiceUsageOaReverseApiRoutes` now owns all `/api/input-invoice-usage/oa-reverse*` HTTP mapping:
  - preview;
  - submitted history;
  - staged drafts;
  - batch create;
  - batch get;
  - one-step draft create;
  - batch draft create;
  - draft revoke;
  - status refresh;
  - manual OA status.
- `server.py` now assembles the route owner and keeps platform helper ports:
  - `_input_invoice_usage_oa_reverse_service`;
  - `_target_oa_applicant_token_provider`;
  - `_input_invoice_usage_oa_draft_client_for_batch`;
  - `_input_invoice_usage_mutation_actor`;
  - `_input_invoice_usage_oa_reverse_error_response`;
  - `_int_or_none`.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:input-invoice-usage-oa-reverse-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-route-owner-facade-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-draft-mutation-route-callback-collapse-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`
   - `backend/src/fin_ops_platform/app/server.py` around OA reverse dispatch/factory/helper ports.
   - `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before declaring local closure.
4. Audit whether OA reverse route-owner local support is fully accounted for:
   - no `_handle_api_input_invoice_usage_oa_reverse_*` route handler remains in `server.py`;
   - all `/api/input-invoice-usage/oa-reverse*` HTTP mapping is route-owned;
   - business state transitions remain in `InputInvoiceUsageOaReverseService`;
   - remaining `Application` methods are dependency assembly, auth/session/platform ports, OA provider/client ports, or error/parse helpers;
   - rows/filter-options/export/read-model fresh gates are out of scope and unchanged.
5. Write an analysis file and update state/docs.
6. If local support is accounted for, select the next residual `server.py` boundary from queue/global audit; if a gap remains, create the next bounded implementation prompt.
7. Commit/push if verification passes.

## Stop Gates

- Do not claim whole input-invoice-usage or global modular closure from this audit.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not touch rows/filter-options/export/read-model fresh gates.
