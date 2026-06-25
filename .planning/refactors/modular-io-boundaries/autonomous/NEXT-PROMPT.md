# Next Prompt

Continue after `server-py:output-invoice-collection-read-model-fresh-gate-service-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:output-invoice-collection-read-model-fresh-gate-service-extraction`.
- Row361 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-read-model-fresh-gate-service-extraction-2026-06-25.md`.
- Output collection route ownership is locally accounted for.
- Output collection SQL read-model fresh gate/source-version/schema stale/all-rows/detail behavior now lives in `OutputInvoiceCollectionReadModelFreshGateService`.
- Output collection module/global closure is not claimed.

## Previous Prompt Completion

`server-py:output-invoice-collection-read-model-fresh-gate-service-extraction` is complete:

- app-owned output collection rows/all-rows/relation-detail helpers now delegate to the fresh-gate service;
- old app-owned schema stale and shared invoice-relation helper implementations were removed;
- `readModelStatus` compatibility and relation detail fail-closed behavior are preserved;
- output collection API regressions, fresh-gate service tests and static guards pass.

## Next Boundary

`server-py:output-invoice-collection-post-fresh-gate-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-read-model-fresh-gate-service-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-output-invoice-collection-mutation-route-callback-collapse-2026-06-25.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `backend/src/fin_ops_platform/app/server.py` around remaining output collection factories/helpers
   - `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
   - `backend/src/fin_ops_platform/services/output_invoice_collection_read_model_fresh_gate_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - `tests/test_output_invoice_collection_api.py`
3. Use CodeGraph before implementation-oriented changes.
4. Audit remaining output collection app-owned surfaces:
   - distinguish dependency assembly/platform ports from business/freshness/payload implementation;
   - confirm whether remaining helpers are acceptable explicit ports or still implementation gaps;
   - select the next precise local implementation boundary if a residual gap remains.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim output collection module/global closure unless the audit proves no local implementation gap remains and explicitly defers only real PostgreSQL/worker/App Status/high-row/browser evidence.
- Do not weaken stale/source-version/schema/fail-closed checks.
- Do not broaden into unrelated `server.py` domains.
