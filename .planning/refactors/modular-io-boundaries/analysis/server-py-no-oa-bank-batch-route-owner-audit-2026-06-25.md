# server-py:no-oa-bank-batch-route-owner-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Module closure:** implementation-gap-open

## Scope

Audit no-OA bank batch route ownership in `server.py` after bank-details route-owner local support was accounted for.

This was an analysis-only slice. It did not change runtime code, API behavior, no-OA business rules, read models, workers, frontend code or production data.

## Current Route Callback Inventory

`server.py` currently owns dispatch and thin HTTP wrappers for:

- `GET /api/no-oa-bank-batches` -> `_handle_api_no_oa_bank_batches(query)`
- `GET /api/no-oa-bank-batches/tag-selection` -> `_handle_api_no_oa_bank_batch_tag_selection()`
- `PUT /api/no-oa-bank-batches/tag-selection` -> `_handle_api_no_oa_bank_batch_tag_selection_update(body, headers)`
- `POST /api/no-oa-bank-batches/submit` -> `_handle_api_no_oa_bank_batches_bulk_submit(body, headers)`
- `POST /api/no-oa-bank-batches/submit-selection` -> `_handle_api_no_oa_bank_batches_submit_selection(body, headers)`
- `GET /api/no-oa-bank-batches/{batch_id}` -> `_handle_api_no_oa_bank_batch_detail(batch_id)`
- `POST /api/no-oa-bank-batches/{batch_id}/submit` -> `_handle_api_no_oa_bank_batch_submit(batch_id, body, headers)`
- `POST /api/no-oa-bank-batches/{batch_id}/withdraw` -> `_handle_api_no_oa_bank_batch_withdraw(batch_id, body, headers)`

## Existing Ownership

`NoOaBankBatchApiRoutes` already owns the route-level business/API methods:

- `list_batches(...)`
- `detail(...)`
- `tag_selection(...)`
- `update_tag_selection(...)`
- `submit_batch(...)`
- `withdraw_batch(...)`
- `submit_selection(...)`
- `bulk_submit(...)`
- structured error mapping for unknown batch, persistence errors, value errors and relation freshness conflicts

`NoOaBankBatchApplicationService` already owns application behavior:

- SQL read model list/detail fallback and freshness semantics
- tag selection persistence and refresh enqueue
- submit/withdraw relation command service delegation
- bulk mutation persistence through `after_mutation(...)`
- source version and stale reason contracts
- durable queue enqueue and explicit mutation persistence boundary

## Classification

All inventoried `server.py` callbacks are thin HTTP wrappers around existing route/application boundaries.

Safe route-owner collapse candidates:

- list/detail/tag-selection reads: move dispatch and JSON response mapping into `NoOaBankBatchApiRoutes.route(...)`;
- tag-selection PUT, bulk submit, submit-selection, batch submit and withdraw: move body/session wrapper into `NoOaBankBatchApiRoutes.route(...)` using explicit ports for mutation-session resolution, JSON body loading and JSON response mapping;
- path parameter parsing for `{batch_id}` can move to route owner with `unquote(...)`.

Do not move these into route code:

- relation command side effects;
- read-model refresh enqueue or dirty/outbox writes;
- persistence/rollback behavior;
- workbench rebuild or search-cache invalidation;
- source-version or stale-reason calculation.

Those are already application-service or lower-layer responsibilities.

## Next Boundary Selection

Selected next implementation boundary:

`server-py:no-oa-bank-batch-route-callback-collapse`

Acceptance criteria:

- add a `route(...)` method to `NoOaBankBatchApiRoutes`;
- inject explicit `resolve_mutation_session`, `load_json_body` and `json_response` ports from `Application`;
- delegate all `/api/no-oa-bank-batches*` dispatch from `server.py` to the route owner;
- remove the eight app-owned no-OA bank batch route callbacks from `server.py`;
- preserve response shape, permission behavior, body parsing errors, unknown batch handling, persistence errors, relation freshness conflicts, affected months and operation barrier fields;
- add route-owner/API/static Guard tests.

## Verification

Passed:

- CodeGraph context for `NoOaBankBatchApiRoutes`, `NoOaBankBatchApplicationService` and no-OA route ownership
- `rg -n "def _handle_api_no_oa_bank_batch|if .*no-oa-bank|/api/no-oa-bank|/api/no-oa" backend/src/fin_ops_platform/app/server.py`
- read of `docs/modules/no-oa-bank-batches/README.md`
- read of `docs/modules/no-oa-bank-batches/tests.md`
- read of `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- read of relevant `server.py` dispatch and callback bodies
- `bash scripts/verify.sh docs`
- `git diff --check`

## Remaining Risk

- No production validation, browser smoke, admin auth evidence or controlled write apply was executed.
- No no-OA module/global closure is claimed.
- Implementation must keep broad no-OA side effects in service/application boundaries and must not turn the route owner into a business orchestrator.
