# Next Prompt

Continue after `server-py:no-oa-bank-batch-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:no-oa-bank-batch-route-owner-audit`.
- Row397 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-route-owner-audit-2026-06-25.md`.
- Eight no-OA bank batch callbacks remain in `server.py`.
- They are thin HTTP dispatch/session/body/json wrappers around existing `NoOaBankBatchApiRoutes` and `NoOaBankBatchApplicationService` behavior.
- No no-OA module/global closure and no production PostgreSQL/worker/App Status/browser/admin/write evidence are claimed.

## Previous Prompt Completion

`server-py:no-oa-bank-batch-route-owner-audit` is complete as analysis-only:

- inventoried all `/api/no-oa-bank-batches*` app-owned callbacks;
- classified all callbacks as safe route-owner collapse candidates;
- kept broad relation, persistence, refresh and worker side effects out of route code;
- selected a single bounded implementation slice.

## Next Boundary

`server-py:no-oa-bank-batch-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-no-oa-bank-batch-route-owner-audit-2026-06-25.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
   - `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
   - `tests/test_no_oa_bank_batch_routes.py`
   - `tests/test_no_oa_bank_batch_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement only no-OA bank batch route callback collapse:
   - add `NoOaBankBatchApiRoutes.route(method, route_path, query, body, headers)`;
   - inject explicit `resolve_mutation_session`, `load_json_body` and `json_response` ports from `Application`;
   - delegate all `/api/no-oa-bank-batches*` dispatch from `server.py` to the route owner;
   - remove `_handle_api_no_oa_bank_batches`, `_handle_api_no_oa_bank_batch_tag_selection`, `_handle_api_no_oa_bank_batch_tag_selection_update`, `_handle_api_no_oa_bank_batch_detail`, `_handle_api_no_oa_bank_batch_submit`, `_handle_api_no_oa_bank_batch_withdraw`, `_handle_api_no_oa_bank_batches_bulk_submit` and `_handle_api_no_oa_bank_batches_submit_selection`;
   - preserve API response shape, permission behavior, body parsing errors, unknown batch handling, persistence errors and relation freshness conflicts.
4. Add route-owner/API/static Guard tests, update docs/state/queue/next prompt, then commit/push if verification passes.

## Stop Gates

- Do not run production validation or mutation.
- Do not move relation command side effects, read-model refresh enqueue, dirty/outbox writes, persistence/rollback behavior, workbench rebuild, search-cache invalidation, source-version or stale-reason calculation into route code.
- Do not change no-OA bank batch business behavior, read model, dirty/outbox, cache, frontend behavior or production data.
- Do not claim no-OA module/global closure.
