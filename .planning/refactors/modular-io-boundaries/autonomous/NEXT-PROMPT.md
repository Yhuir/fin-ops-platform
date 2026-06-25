# Next Prompt

Continue after `server-py:output-invoice-collection-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:output-invoice-collection-route-owner-audit`.
- Row357 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-route-owner-audit-2026-06-25.md`.
- Output collection has an existing `OutputInvoiceCollectionApiRoutes` route owner.
- `server.py` still owns direct dispatch branches and thin `_handle_api_output_invoice_collections*` callbacks.
- Output collection module/global closure is not claimed.

## Previous Prompt Completion

`server-py:output-invoice-collection-route-owner-audit` is complete:

- classified read/export/status/history/detail callbacks as thin HTTP/session/response wrappers;
- classified lifecycle/receipt/red-relation/receipt-settings write callbacks as later mutation work;
- classified output collection SQL fresh-gate helpers as a later fresh-gate extraction surface;
- selected a bounded read/export route callback collapse first.

## Next Boundary

`server-py:output-invoice-collection-read-export-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-route-owner-audit-2026-06-25.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around output collection dispatch and read/export callbacks
   - `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
   - `tests/test_output_invoice_collection_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before code changes.
4. Implement narrowly:
   - add a route method or equivalent HTTP mapping to `OutputInvoiceCollectionApiRoutes` for read/export/status/history/detail routes;
   - inject explicit ports for read session resolution, JSON response, XLSX response, error mapping and route path decoding as needed;
   - remove migrated app-owned read/export/status/history/detail callbacks from `server.py`;
   - keep lifecycle mutation callbacks, receipt preview/settings update and fresh-gate helpers out of scope.
5. Update static Guard and targeted output collection API regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change output collection response shape, permissions, status codes or XLSX headers.
- Do not weaken output collection freshness/source-version/schema/fail-closed semantics.
- Do not move mutation callbacks in the same slice unless the diff remains narrow and tests clearly cover it.
- Do not extract output collection fresh gate in this slice.
- Do not run production validation or mutation.
