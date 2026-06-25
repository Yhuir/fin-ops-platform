# Next Prompt

Continue after `server-py:input-invoice-usage-payment-rules-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-payment-rules-route-callback-collapse`.
- Row353 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-payment-rules-route-callback-collapse-2026-06-25.md`.
- `InputInvoiceUsageApiRoutes` owns input usage rows/filter/detail/relation/payment GET, export preview/download and payment rules PUT HTTP mapping.
- `server.py` no longer owns the input usage export or payment rules PUT callbacks.
- Input usage module/global closure is not claimed.

## Previous Prompt Completion

`server-py:input-invoice-usage-payment-rules-route-callback-collapse` is locally implemented:

- payment rules PUT moved into `InputInvoiceUsageApiRoutes`;
- explicit settings/body/error/refresh ports are injected from `Application`;
- payment rules save regression now uses the public route;
- route-owner Guard prevents the private handler from returning.

## Next Boundary

`server-py:input-invoice-usage-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-payment-rules-route-callback-collapse-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`
   - `backend/src/fin_ops_platform/app/server.py` input usage helper/factory/dispatch surfaces
   - `tests/test_platform_runtime_boundary_guards.py`
   - `docs/modules/input-invoice-usage/implementation-notes.md`
3. Use CodeGraph before classifying residual `Application` methods.
4. Audit remaining input usage surfaces in `server.py`:
   - route dispatch and route owner factory;
   - query/export/payment helper ports;
   - SQL read-model fresh-gate/detail helper ports;
   - payment rules refresh producer;
   - OA reverse provider/client/platform helper ports;
   - error response mappers and response serializers.
5. Classify each residual as:
   - dependency assembly;
   - HTTP/platform mapping;
   - read-model/freshness port;
   - refresh producer port;
   - external/OA platform port;
   - compat-only wrapper;
   - implementation gap.
6. Write the analysis file and update state/docs.
7. If the audit finds a concrete implementation gap, generate and execute that next bounded slice immediately.

## Stop Gates

- Do not claim whole input usage module/global closure from route-owner support alone.
- Do not move read-model fresh-gate helpers or OA provider/client helpers without a dedicated boundary.
- Do not run production validation or perform production mutation.
- Do not weaken static Guard coverage for input usage route ownership.
