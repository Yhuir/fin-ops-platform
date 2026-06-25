# Next Prompt

Continue after `server-py:input-invoice-usage-post-fresh-gate-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:input-invoice-usage-post-fresh-gate-local-closure-audit`.
- Row356 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-post-fresh-gate-local-closure-audit-2026-06-25.md`.
- Input usage local `server.py` support is accounted for after route-owner collapse and fresh-gate extraction.
- Remaining input usage app methods are dependency/platform/refresh/source-version/import-scope provider ports.
- Input usage module/global closure is not claimed.

## Previous Prompt Completion

`server-py:input-invoice-usage-post-fresh-gate-local-closure-audit` is complete:

- no `_handle_api_input_invoice_usage*` callback remains in `server.py`;
- no input usage app-owned SQL payload schema helper remains;
- no input usage app-owned export row-page loader remains;
- no input usage app-owned fresh/stale/source-version response assembly remains;
- output invoice collection was identified as the next adjacent `server.py` residual surface.

## Next Boundary

`server-py:output-invoice-collection-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-input-invoice-usage-post-fresh-gate-local-closure-audit-2026-06-25.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around `/api/output-invoice-collections*` dispatch and `_handle_api_output_invoice_collections*`
   - `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
   - `tests/test_output_invoice_collection_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before implementation-oriented changes.
4. Audit output collection route ownership:
   - identify which app callbacks are thin HTTP/session/body/response wrappers;
   - identify which callbacks still own lifecycle, receipt, red invoice, reminder or fresh-gate implementation;
   - split route-owner callback collapse from broader service/fresh-gate extraction if needed;
   - select the smallest safe next local implementation boundary.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change output collection behavior in the audit.
- Do not weaken output collection freshness/source-version/schema/fail-closed semantics.
- Do not collapse route callbacks that still own broad lifecycle/receipt/fresh-gate logic without a separate implementation plan.
- Do not claim output collection module/global closure from route-owner accounting alone.
- Do not run production validation or mutation while local implementation gaps remain.
