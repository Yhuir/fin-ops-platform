# Next Prompt

Continue after `server-py:tax-offset-read-plan-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:tax-offset-read-plan-route-callback-collapse`.
- Row372 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-tax-offset-read-plan-route-callback-collapse-2026-06-25.md`.
- Tax offset month/summary/calculate/plan-save/import-job/certified-imports list HTTP mapping now lives in `TaxApiRoutes.route(...)`.
- Certified import preview/confirm callbacks remain in `server.py`.
- Tax module/global closure and production PostgreSQL/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:tax-offset-read-plan-route-callback-collapse` is complete:

- added `TaxApiRoutes.route(...)`;
- injected read/mutation session, JSON body, actor-id and certified-records ports;
- removed migrated app callbacks;
- preserved certified import preview/confirm callbacks in `server.py`;
- added static Guard coverage.

## Next Boundary

`server-py:tax-certified-import-route-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-tax-offset-read-plan-route-callback-collapse-2026-06-25.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_tax.py`
   - `tests/test_tax_offset_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining certified import preview/confirm callbacks:
   - multipart parsing and upload normalization;
   - preview application service ownership;
   - confirm session id validation;
   - import queue/idempotency metadata;
   - inline execution fallback and error mapping.
4. Select one bounded local implementation or analysis slice.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not change certified import preview/confirm behavior or import job response shape.
- Do not run production validation or mutation.
- Do not claim tax module/global closure from this slice.
- Do not broaden into unrelated domains.
