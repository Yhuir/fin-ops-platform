# Next Prompt

Continue after `server-py:input-invoice-usage-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-route-owner-local-closure-audit`.
- Row354 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-route-owner-local-closure-audit-2026-06-25.md`.
- Input usage route callback ownership is locally accounted for.
- `server.py` still owns input usage SQL read-model fresh gate/source-version/export row-page helper logic.
- Input usage module/global closure is not claimed.

## Previous Prompt Completion

`server-py:input-invoice-usage-route-owner-local-closure-audit` is complete:

- no audited input usage route callbacks remain in `server.py`;
- route owner factories and HTTP/platform ports are accounted for;
- remaining implementation gap is read-model fresh gate/query/export row-page logic still living in `Application`;
- next safe local implementation is a focused extraction, not production validation.

## Next Boundary

`server-py:input-invoice-usage-read-model-fresh-gate-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-route-owner-local-closure-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around input usage read-model helpers
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
   - existing input usage read-model/detail services and tests
   - `tests/test_input_invoice_usage_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing.
4. Implement narrowly:
   - extract input usage SQL read-model rows fresh gate out of `Application`;
   - include all-rows aggregation and relation detail fresh gate only if they can share the same explicit adapter without pulling output collection behavior into the slice;
   - route export row-page loading through the extracted adapter/service;
   - preserve production SQL-repository-unavailable fail-closed behavior;
   - keep output invoice collection behavior unchanged.
5. Update static Guard and targeted API/export/refreshing regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change output invoice collection behavior unless a targeted shared-helper regression proves it is preserved.
- Do not weaken stale/source-version/schema/fail-closed checks.
- Do not change export response shape or refreshing semantics.
- Do not run production validation or mutation.
- Do not claim input usage module/global closure from this extraction alone.
