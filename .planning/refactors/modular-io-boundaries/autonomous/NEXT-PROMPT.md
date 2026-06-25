# Next Prompt

Continue after `server-py:input-invoice-usage-oa-reverse-draft-mutation-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-oa-reverse-draft-mutation-callback-audit`.
- Row345 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-draft-mutation-callback-audit-2026-06-25.md`.
- `InputInvoiceUsageOaReverseApiRoutes` already owns lightweight OA reverse HTTP mapping for preview/history/staged/batch create/get.
- `server.py` still owns five OA reverse mutation HTTP callbacks:
  - one-step draft create;
  - batch draft create;
  - batch draft revoke;
  - status refresh;
  - manual OA status.
- The audit found those callbacks are safe to collapse into the existing route owner if the route owner receives only explicit ports:
  - `target_oa_applicant_token_provider`;
  - `oa_draft_client_for_batch`;
  - `int_or_none`;
  - existing `mutation_actor`;
  - existing `load_json_body`;
  - existing `json_response`;
  - existing `oa_reverse_error_response`.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:input-invoice-usage-oa-reverse-draft-mutation-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-oa-reverse-draft-mutation-callback-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`
   - `backend/src/fin_ops_platform/app/server.py` around the five remaining OA reverse mutation handlers and route dispatch.
   - `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing.
4. Implement the callback collapse:
   - extend `InputInvoiceUsageOaReverseApiRoutes.route(...)` to handle:
     - `POST /api/input-invoice-usage/oa-reverse/oa-draft`;
     - `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft`;
     - `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft/revoke`;
     - `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-status/refresh`;
     - `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/manual-oa-status`.
   - add explicit constructor ports for target OA provider, per-batch draft client provider and int parsing;
   - remove the five legacy mutation handlers from `server.py`;
   - keep `_target_oa_applicant_token_provider(...)`, `_input_invoice_usage_oa_draft_client_for_batch(...)`, `_input_invoice_usage_mutation_actor(...)`, `_input_invoice_usage_oa_reverse_error_response(...)` and `_int_or_none(...)` as platform/helper ports unless a separate audit proves otherwise.
5. Add/extend static Guard and run targeted OA reverse API regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change OA reverse response shape, status codes, permission behavior, idempotency, version conflict or read model invalidation.
- Do not move OA token/header parsing into services.
- Do not pass the whole `Application` into route owner or services.
- Do not touch rows/filter-options/export/read-model fresh gates.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
