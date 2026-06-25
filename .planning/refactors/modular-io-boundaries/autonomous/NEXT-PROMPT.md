# Next Prompt

Continue after `server-py:bank-details-route-owner-local-closure-audit-retry`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:bank-details-route-owner-local-closure-audit-retry`.
- Row396 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-route-owner-local-closure-audit-retry-2026-06-25.md`.
- Bank-details route-owner local support is accounted for: no app-owned bank-details route callback remains in `server.py`.
- Bank-details module/global closure and production PostgreSQL/worker/App Status/browser/admin/write evidence are not claimed.
- `server.py` still has app-owned route callbacks for other modules.

## Previous Prompt Completion

`server-py:bank-details-route-owner-local-closure-audit-retry` is complete as analysis-only:

- proved bank-details route callbacks are owned by `BankDetailsApiRoutes.route(...)`;
- classified remaining bank-related `Application` methods as composition-root, HTTP/platform adapter, read-model/source-version/refresh provider or shared downstream support;
- avoided runtime code changes and avoided production validation;
- selected no-OA bank batch route-owner audit next.

## Next Boundary

`server-py:no-oa-bank-batch-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-bank-details-route-owner-local-closure-audit-retry-2026-06-25.md`
   - `docs/modules/README.md`
   - any no-OA bank batch module docs under `docs/modules/`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - relevant `tests/test_no_oa*` and `tests/test_platform_runtime_boundary_guards.py`
3. Audit only no-OA bank batch route ownership:
   - inventory `_handle_api_no_oa_bank_batch*` callbacks in `server.py`;
   - classify callbacks as thin HTTP wrappers, route-owner collapse candidates, or service/side-effect extraction candidates;
   - identify the smallest next local implementation boundary.
4. Update analysis/state/queue/journal/next prompt and commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not move broad persistence, refresh, relation repair or worker side effects into route code.
- Do not change no-OA bank batch business behavior, read model, dirty/outbox, cache, frontend behavior or production data during the audit.
- Do not claim global closure.
