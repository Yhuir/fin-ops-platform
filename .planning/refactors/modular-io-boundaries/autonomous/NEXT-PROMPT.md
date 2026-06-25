# Next Prompt

Continue after `server-py:output-invoice-collection-mutation-route-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:output-invoice-collection-mutation-route-callback-audit`.
- Row359 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-mutation-route-callback-audit-2026-06-25.md`.
- Output collection read/export/status/history/detail HTTP mapping already lives in `OutputInvoiceCollectionApiRoutes`.
- Remaining output collection callbacks are thin body/session/error/trace/idempotency wrappers around route-owner methods.
- Output collection SQL fresh-gate helpers still live in `Application`.
- Output collection module/global closure is not claimed.

## Previous Prompt Completion

`server-py:output-invoice-collection-mutation-route-callback-audit` is complete:

- classified receipt preview/settings and lifecycle/receipt/red-relation callbacks as thin HTTP wrappers;
- confirmed business rules live in route owner plus lifecycle/receipt services;
- selected mutation callback collapse with a `load_json_body` port as the next bounded implementation slice;
- kept SQL fresh-gate extraction out of scope.

## Next Boundary

`server-py:output-invoice-collection-mutation-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-read-export-route-callback-collapse-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-mutation-route-callback-audit-2026-06-25.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around remaining `_handle_api_output_invoice_collections*` callbacks
   - `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
   - `tests/test_output_invoice_collection_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before code changes.
4. Implement narrowly:
   - inject `load_json_body` into `OutputInvoiceCollectionApiRoutes`;
   - extend `route(...)` to own receipt preview, receipt settings GET/PUT, collection status/reminder create/delete, red relation create/delete, and receipt create/void/reissue;
   - preserve `x-request-id` trace id propagation;
   - preserve `Idempotency-Key` / `idempotency-key` mapping for receipt create;
   - remove the remaining `_handle_api_output_invoice_collections*` callbacks and `_output_invoice_collection_mutation(...)` from `server.py`;
   - do not change SQL fresh-gate helpers.
5. Update static Guard and targeted output collection API regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change output collection lifecycle/receipt business behavior.
- Do not weaken permissions, idempotency key handling, trace id propagation or freshness target response contracts.
- Do not extract output collection fresh gate in this slice.
- Do not run production validation or mutation.
