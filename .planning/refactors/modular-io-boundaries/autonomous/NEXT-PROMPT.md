# Next Prompt

Continue after `server-py:output-invoice-collection-mutation-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:output-invoice-collection-mutation-route-callback-collapse`.
- Row360 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-mutation-route-callback-collapse-2026-06-25.md`.
- Output collection route ownership is locally accounted for; all output collection HTTP mapping now lives in `OutputInvoiceCollectionApiRoutes`.
- Output collection SQL fresh-gate helpers still live in `Application`.
- Output collection module/global closure is not claimed.

## Previous Prompt Completion

`server-py:output-invoice-collection-mutation-route-callback-collapse` is complete:

- route owner now handles receipt preview/settings and lifecycle/receipt/red-relation mutations;
- `load_json_body` is an explicit route-owner port;
- idempotency and trace headers are preserved;
- all `_handle_api_output_invoice_collections*` callbacks and `_output_invoice_collection_mutation(...)` were removed from `server.py`;
- output collection API regressions and static route-owner guards pass.

## Next Boundary

`server-py:output-invoice-collection-read-model-fresh-gate-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-mutation-route-callback-collapse-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-route-owner-audit-2026-06-25.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around output collection SQL read-model helpers
   - `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
   - existing output collection read-model/detail services and tests
   - `tests/test_output_invoice_collection_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - `tests/test_read_model_architecture_guards.py`
3. Use CodeGraph before code changes.
4. Implement narrowly:
   - extract output collection SQL read-model rows fresh gate out of `Application`;
   - include all-rows aggregation and relation detail fresh gate only if they can share the same explicit adapter without changing input usage behavior;
   - preserve production SQL-repository-unavailable fail-closed behavior;
   - preserve output collection lifecycle overlay behavior and `readModelStatus` compatibility fields;
   - keep input usage behavior unchanged.
5. Update static Guard and targeted API/export/refreshing regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change input usage behavior.
- Do not weaken output collection stale/source-version/schema/fail-closed checks.
- Do not change export response shape, relation detail payload shape or lifecycle overlay semantics.
- Do not run production validation or mutation.
