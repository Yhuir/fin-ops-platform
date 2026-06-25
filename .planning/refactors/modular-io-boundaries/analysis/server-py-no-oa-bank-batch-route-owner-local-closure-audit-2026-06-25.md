# server-py:no-oa-bank-batch-route-owner-local-closure-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Module closure:** implementation-gap-open

## Scope

Re-audit no-OA bank batch `server.py` route/support surfaces after all `/api/no-oa-bank-batches*` callbacks moved into `NoOaBankBatchApiRoutes.route(...)`.

This was an analysis-only slice. It did not change runtime code, API behavior, no-OA business rules, read models, workers, frontend code or production data.

## Route Ownership Evidence

No app-owned no-OA route callbacks remain in `server.py`:

- no `_handle_api_no_oa_bank_batch*` definitions remain;
- `/api/no-oa-bank-batches*` dispatch delegates to `self._no_oa_bank_batch_routes().route(method, route_path, query, body, headers)`;
- endpoint matching and path parsing now live in `routes_no_oa_bank_batches.py`.

## Remaining Application Surfaces

Remaining no-OA bank batch `Application` methods classify as:

- composition root / dependency assembly:
  - `_no_oa_bank_batch_application_service(...)`
  - `_no_oa_bank_batch_routes(...)`
  - `_no_oa_bank_batch_derived_lifecycle_executor(...)`
- HTTP/platform adapter:
  - `_no_oa_bank_batch_mutation_session(...)`
- source-version/read-model/refresh support:
  - `_enqueue_no_oa_bank_batch_read_model_refreshes(...)`
  - `_no_oa_bank_batch_workbench_source_versions(...)`
- Workbench payload decoration support:
  - `_relation_with_no_oa_bank_batch_metadata(...)`
  - `_apply_no_oa_bank_batch_pair_metadata(...)`
  - `_apply_no_oa_bank_batch_available_actions(...)`

## Closure Decision

No-OA route callbacks are accounted for, but no-OA `server.py` local support is not fully closed.

The immediate implementation gap is `_enqueue_no_oa_bank_batch_read_model_refreshes(...)`: it owns no-OA scope normalization and direct `ReadModelRefreshGateway.enqueue_many("no_oa_bank_batch", ...)` calls inside `Application`. This is not HTTP route ownership, but it is still local modular IO implementation logic in `server.py`.

## Next Boundary Selection

Selected next implementation boundary:

`server-py:no-oa-bank-batch-refresh-producer-extraction`

Acceptance criteria:

- introduce a no-OA-specific read model refresh producer/service in `services/`;
- move no-OA scope normalization and gateway enqueue behavior out of `Application`;
- keep `Application` as dependency assembly only;
- update no-OA application service and derived lifecycle wiring to use the producer;
- preserve accepted scopes (`all` and `YYYY-MM`), dedupe semantics, reason forwarding and false return when gateway cannot enqueue;
- add service/static Guard tests preventing direct no-OA gateway enqueue from returning to `server.py`.

## Verification

Passed:

- CodeGraph context for `NoOaBankBatchApiRoutes`, `NoOaBankBatchApplicationService` and no-OA route ownership
- `rg -n "def _handle_api_no_oa_bank_batch|_handle_api_no_oa_bank_batch|/api/no-oa-bank-batches|_no_oa_bank_batch_routes\\(\\)\\.route|def _.*no_oa_bank_batch" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `rg -n "_enqueue_no_oa_bank_batch_read_model_refreshes|_no_oa_bank_batch_workbench_source_versions|_relation_with_no_oa_bank_batch_metadata|_apply_no_oa_bank_batch_pair_metadata|_apply_no_oa_bank_batch_available_actions|_no_oa_bank_batch_derived_lifecycle_executor|_no_oa_bank_batch_mutation_session" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services -g '*.py'`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Remaining Risk

- No production validation, browser smoke, admin auth evidence or controlled write apply was executed.
- No no-OA module/global closure is claimed.
- Workbench payload decoration helpers remain a possible later support-boundary audit after refresh producer extraction.
