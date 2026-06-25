# Next Prompt

Continue after `server-py:no-oa-bank-batch-route-callback-collapse`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:no-oa-bank-batch-route-callback-collapse`.
- Row398 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-route-callback-collapse-2026-06-25.md`.
- `NoOaBankBatchApiRoutes.route(...)` owns `/api/no-oa-bank-batches*` HTTP mapping.
- Eight app-owned no-OA route callbacks are removed from `server.py`.
- No no-OA route-owner closure audit, module/global closure or production PostgreSQL/worker/App Status/browser/admin/write evidence is claimed.

## Previous Prompt Completion

`server-py:no-oa-bank-batch-route-callback-collapse` is complete locally:

- added route-owner dispatch and explicit platform ports;
- removed no-OA route callbacks from `server.py`;
- preserved API behavior with route tests and public API regression tests;
- added static Guard coverage.

## Next Boundary

`server-py:no-oa-bank-batch-route-owner-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-route-callback-collapse-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Audit only no-OA bank batch route ownership:
   - prove no `_handle_api_no_oa_bank_batch*` callbacks remain in `server.py`;
   - confirm `/api/no-oa-bank-batches*` dispatch delegates to `NoOaBankBatchApiRoutes.route(...)`;
   - classify remaining `Application` surfaces as composition-root, provider, auth/session, HTTP adapter, read-model/source-version/refresh or platform ports;
   - do not claim module/global closure unless all local implementation definitions are actually satisfied.
4. Update analysis/state/queue/journal/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not change no-OA bank batch business behavior, read model, refresh, dirty/outbox, cache, frontend behavior or production data.
- Do not claim global closure.
- If a remaining no-OA app-owned callback or implementation helper is found, select the next narrow local implementation boundary instead of closing.
