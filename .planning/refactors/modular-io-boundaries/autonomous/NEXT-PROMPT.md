# Next Prompt

Continue after `server-py:input-invoice-usage-read-model-fresh-gate-service-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-read-model-fresh-gate-service-extraction`.
- Row355 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-read-model-fresh-gate-service-extraction-2026-06-25.md`.
- Input usage route-owner callbacks have been collapsed into route owner classes.
- Input usage SQL read-model fresh gate/source-version/schema stale/all-rows/detail/export row-page behavior now lives in `InputInvoiceUsageReadModelFreshGateService`.
- Output invoice collection behavior was intentionally left unchanged and covered by targeted regression.
- Input usage module/global closure is not claimed.

## Previous Prompt Completion

`server-py:input-invoice-usage-read-model-fresh-gate-service-extraction` is complete:

- `server.py` no longer owns `_load_input_invoice_usage_export_page(...)`, `_input_invoice_usage_export_query_from_kwargs(...)` or `_input_invoice_usage_sql_payload_requires_schema_refresh(...)`;
- app-owned input usage rows/all-rows/relation-detail helpers delegate to the fresh-gate service;
- export row-page loading uses the fresh-gate service;
- refreshing/fail-closed semantics are preserved for missing SQL repository, schema stale, stale refresh status and source-version mismatch;
- static guards prevent the removed app-owned fresh-gate helpers from returning.

## Next Boundary

`server-py:input-invoice-usage-post-fresh-gate-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-route-owner-local-closure-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-read-model-fresh-gate-service-extraction-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around input usage factories and remaining `_input_invoice_usage*` helpers
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`
   - `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`
   - `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_fresh_gate_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - `tests/test_input_invoice_usage_api.py`
3. Use CodeGraph before implementation-oriented changes.
4. Audit remaining input usage app-owned surfaces:
   - distinguish route dispatch/dependency assembly/platform ports from business/freshness/payload implementation;
   - confirm whether remaining helpers are acceptable explicit ports or are still implementation gaps;
   - select the next precise local implementation boundary if a residual gap remains.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim input usage module/global closure unless the audit proves no local implementation gap remains and explicitly defers only real PostgreSQL/worker/App Status/high-row/browser evidence.
- Do not weaken stale/source-version/schema/fail-closed checks.
- Do not change output invoice collection behavior.
- Do not broaden into unrelated `server.py` domains.
