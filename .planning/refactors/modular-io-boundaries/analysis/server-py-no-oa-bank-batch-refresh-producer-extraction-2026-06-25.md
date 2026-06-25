# server-py:no-oa-bank-batch-refresh-producer-extraction

## Status

- Boundary: `server-py:no-oa-bank-batch-refresh-producer-extraction`
- Result: `local-implementation-closed`
- Module closure: `implementation-gap-open`
- Production evidence: `production-evidence-deferred`
- Worker threads: none; the slice touched one shared `server.py` area plus one no-OA service boundary, so inline T0 execution avoided same-file worker conflicts.

## Goal

Move no-OA bank batch read model refresh scope normalization and durable queue enqueue ownership out of `Application` and into an explicit no-OA producer service.

This is a local modularity slice only. It does not change no-OA business rules, API response shape, read model schema, dirty/outbox schema, frontend behavior, permissions, audit semantics or production data.

## Pre-implementation Findings

- `NoOaBankBatchApiRoutes.route(...)` already owns `/api/no-oa-bank-batches*` dispatch after the route callback collapse slice.
- No `_handle_api_no_oa_bank_batch*` callbacks remain in `server.py`.
- Remaining gap found by the previous audit: `Application._enqueue_no_oa_bank_batch_read_model_refreshes(...)` still owned:
  - accepted scope filtering for `all` and `YYYY-MM`;
  - invalid/empty scope fallback to `all`;
  - direct `ReadModelRefreshGateway.enqueue_many("no_oa_bank_batch", ...)` calls;
  - no-OA refresh callback wiring for tag selection, application service and derived lifecycle executor.

## Implementation

- Added `NoOaBankBatchReadModelRefreshProducer`.
- Moved no-OA scope normalization into `NoOaBankBatchReadModelRefreshProducer.normalize_scope_keys(...)`.
- Kept non-transactional durable enqueue behind `ReadModelRefreshGateway` through the existing provider boundary.
- Added `Application._no_oa_bank_batch_read_model_refresh_producer(...)` as dependency assembly only.
- Wired `NoOaBankBatchApplicationService` with `read_model_refresh_producer`.
- Wired `NoOaBankBatchDerivedLifecycleExecutor` through `NoOaBankBatchReadModelRefreshProducer.enqueue`.
- Updated tag-selection refresh callback to use the producer.
- Removed `Application._enqueue_no_oa_bank_batch_read_model_refreshes(...)`.

## Preserved Contracts

- Accepted no-OA read model refresh scopes remain `all` and `YYYY-MM`.
- Invalid or empty scope lists still fall back to `["all"]`.
- Scope de-duplication preserves first-seen order.
- `reason` and optional `metadata` continue to be forwarded to the gateway.
- When the gateway cannot enqueue, the producer returns `False`/empty result and does not call `enqueue_many(...)`.
- `NoOaBankBatchApplicationService.enqueue_background_refresh(...)` preserves a fallback `queue_repository` path for existing local tests/non-production construction, but production `Application` wiring now prefers the injected producer.

## Boundary Evidence

- `server.py` no longer defines `_enqueue_no_oa_bank_batch_read_model_refreshes(...)`.
- `server.py` no longer directly calls `enqueue_many("no_oa_bank_batch", ...)`.
- `NoOaBankBatchReadModelRefreshProducer` owns scope normalization and gateway enqueue.
- `NoOaBankBatchApplicationService.enqueue_background_refresh(...)` prefers the injected producer.
- `NoOaBankBatchDerivedLifecycleExecutor` receives the producer enqueue method from `Application` dependency assembly.

## Tests Added Or Changed

- Added `tests/test_no_oa_bank_batch_read_model_refresh_producer.py`
  - covers scope normalization, reason/metadata forwarding, invalid-scope fallback and unavailable-gateway behavior.
- Updated `tests/test_no_oa_bank_batch_application_service.py`
  - adds `test_enqueue_background_refresh_uses_injected_refresh_producer`.
  - keeps the existing durable queue fallback regression.
- Updated `tests/test_platform_runtime_boundary_guards.py`
  - adds `test_no_oa_bank_batch_refresh_enqueue_uses_producer_boundary`.

## Seven Test Categories

- Business core unit tests: not applicable; no no-OA batch lifecycle, classification, submit/withdraw or amount rule changed.
- Service-layer tests: applicable and covered by producer unit tests plus application service injected-producer regression.
- API contract tests: not applicable for new coverage; HTTP routes and response shape did not change in this slice.
- Read model/cache/background job tests: applicable and covered by producer gateway/normalization tests and derived lifecycle executor regression.
- Frontend component and interaction tests: not applicable; page behavior and operation barrier targets did not change.
- End-to-end business-flow integration tests: not applicable for new coverage; no cross-module user flow changed.
- Existing feature regression tests: applicable and covered by the existing durable queue fallback test, derived lifecycle executor tests and platform boundary Guard.

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh_producer.py backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py backend/src/fin_ops_platform/app/server.py tests/test_no_oa_bank_batch_read_model_refresh_producer.py tests/test_no_oa_bank_batch_application_service.py tests/test_no_oa_bank_batch_derived_lifecycle_executor.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh_producer -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service.NoOaBankBatchApplicationServiceTests.test_enqueue_background_refresh_uses_injected_refresh_producer tests.test_no_oa_bank_batch_application_service.NoOaBankBatchApplicationServiceTests.test_enqueue_background_refresh_uses_durable_queue_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_derived_lifecycle_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_refresh_enqueue_uses_producer_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_source_version_helpers_stay_out_of_application -v
```

All commands above passed locally.

## Deferred Evidence And Risks

- No production command was run for this slice.
- No staging database and no local PostgreSQL URL are available.
- Real PostgreSQL/worker/App Status/browser/write-flow closure remains deferred.
- no-OA module/global closure is not claimed from this local producer extraction alone.

## Next Boundary

`server-py:no-oa-bank-batch-post-refresh-producer-local-closure-audit`

Audit remaining no-OA `Application` surfaces after route callback collapse and refresh producer extraction. The audit must classify whether remaining no-OA helpers are only composition-root/platform/provider ports, or whether additional local implementation gaps remain.
