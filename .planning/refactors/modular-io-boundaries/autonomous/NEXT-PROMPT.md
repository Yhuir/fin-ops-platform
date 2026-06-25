# Next Prompt

Continue after `server-py:tax-certified-import-route-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:tax-certified-import-route-callback-audit`.
- Row373 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-tax-certified-import-route-callback-collapse-2026-06-25.md`.
- Tax offset month/summary/calculate/plan-save/import-job/certified-imports list and certified import preview/confirm HTTP mapping now lives in `TaxApiRoutes.route(...)`.
- Tax module/global closure and production PostgreSQL/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:tax-certified-import-route-callback-audit` is complete:

- audited preview/confirm adapter responsibilities;
- moved preview/confirm HTTP mapping into `TaxApiRoutes.route(...)`;
- injected multipart, preview, import queue, serializer and inline confirm executor ports;
- removed migrated app callbacks;
- added static Guard coverage.

## Next Boundary

`server-py:tax-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-tax-certified-import-route-callback-collapse-2026-06-25.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_tax.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining tax `Application` surfaces after route callback collapse:
   - route factory/composition;
   - read/mutation session provider;
   - actor id, multipart/body and import job ports;
   - tax offset runtime/query/read-model/cache/warmup provider surfaces;
   - import processing and derived lifecycle ports.
4. Decide whether tax local `server.py` route-owner support is accounted for, without claiming global/module production closure.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim tax module/global closure unless all local and evidence gates are explicitly satisfied.
- Do not broaden into unrelated domains.
