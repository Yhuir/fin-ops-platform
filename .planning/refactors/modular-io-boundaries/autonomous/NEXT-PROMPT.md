# Next Prompt

Continue after `server-py:tax-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:tax-route-owner-audit`.
- Row371 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-tax-route-owner-audit-2026-06-25.md`.
- Pending invoice local `server.py` route-owner support is accounted for.
- Tax module/global closure and production PostgreSQL/worker/App Status/browser evidence are not claimed.

## Previous Prompt Completion

`server-py:tax-route-owner-audit` is complete:

- audited `TaxApiRoutes` and tax offset `server.py` callbacks;
- selected month/summary/calculate/plan-save/import-job/certified-imports list route callback collapse as the first implementation slice;
- deferred certified import preview/confirm because they own multipart parsing and import queue/inline execution semantics.

## Next Boundary

`server-py:tax-offset-read-plan-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-tax-route-owner-audit-2026-06-25.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_tax.py`
   - `tests/test_tax_offset_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement:
   - add `TaxApiRoutes.route(...)`;
   - inject explicit read-session, mutation-session, JSON body loader and actor-id ports;
   - move month/summary/calculate/plan-save/import-job/certified-imports list HTTP mapping into route owner;
   - remove migrated app callbacks;
   - leave certified import preview/confirm callbacks in `server.py`;
   - add/extend static Guard coverage.
4. Verify with py_compile, `tests.test_tax_offset_api`, targeted platform runtime boundary guards, docs verify and diff checks.
5. Update docs/state and commit/push if verification passes.

## Stop Gates

- Do not change tax calculation, freshness, plan conflict/idempotency, import job response shape or certified import preview/confirm behavior.
- Do not run production validation or mutation.
- Do not claim tax module/global closure from this slice.
- Do not broaden into unrelated domains.
