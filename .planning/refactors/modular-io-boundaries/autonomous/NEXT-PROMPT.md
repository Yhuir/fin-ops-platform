# Next Prompt

Continue after `server-py:output-invoice-collection-read-export-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:output-invoice-collection-read-export-route-callback-collapse`.
- Row358 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-read-export-route-callback-collapse-2026-06-25.md`.
- Output collection read/export/status/history/detail HTTP mapping now lives in `OutputInvoiceCollectionApiRoutes`.
- Remaining output collection app-owned callbacks are receipt preview, receipt settings and lifecycle/receipt/red-relation mutations.
- Output collection SQL fresh-gate helpers still live in `Application`.
- Output collection module/global closure is not claimed.

## Previous Prompt Completion

`server-py:output-invoice-collection-read-export-route-callback-collapse` is complete:

- `Application` delegates output collection read/export/detail route matching through `_output_invoice_collection_routes().route(...)`;
- migrated read/export/status/history/detail callbacks were removed from `server.py`;
- route owner has explicit read-session, JSON, XLSX and error-response ports;
- output collection API regressions and static route-owner guards pass;
- mutation callbacks and fresh-gate helpers were intentionally left out of scope.

## Next Boundary

`server-py:output-invoice-collection-mutation-route-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-route-owner-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-read-export-route-callback-collapse-2026-06-25.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around remaining `_handle_api_output_invoice_collections*` callbacks
   - `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
   - `tests/test_output_invoice_collection_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before implementation-oriented changes.
4. Audit remaining output collection callbacks:
   - receipt preview;
   - receipt settings GET/PUT;
   - collection status/reminder create/delete;
   - red invoice relation create/delete;
   - receipt create/void/reissue;
   - shared `_output_invoice_collection_mutation(...)`.
5. Select the smallest safe next implementation boundary: direct mutation callback collapse, receipt-preview/settings split, or fresh-gate extraction if route callbacks are no longer the highest-risk local gap.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change output collection lifecycle/receipt business behavior in the audit.
- Do not weaken permissions, idempotency key handling, trace id propagation or freshness target response contracts.
- Do not mix fresh-gate extraction with mutation callback collapse unless a separate analysis proves it is narrow.
- Do not run production validation or mutation.
