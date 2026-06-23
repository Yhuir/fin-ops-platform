# Batch Accounting Submit/Withdraw Route Side-Effect Port

**Date:** 2026-06-24
**Boundary:** `batch-accounting:submit-withdraw-route-side-effect-port`
**Status:** implementation slice closed; module implementation gap remains open

## Previous State

- `GET /api/batch-accounting` already delegated to `BatchAccountingApiRoutes.list_payload(...)`.
- `POST /api/batch-accounting/submit` and `POST /api/batch-accounting/{relation_id}/withdraw` still kept DTO parsing, `BatchAccountingError` mapping, service invocation, affected-scope calculation and write-after side effects inline in `server.py`.
- `BatchAccountingService` already owned canonical relation mutation rules and command-service writes.

## Selected Boundary

Move submit/withdraw mutation DTO mapping and write-after side-effect orchestration into `BatchAccountingApiRoutes`, while keeping:

- session/auth resolution in `server.py`;
- JSON body parsing in `server.py`;
- business mutation rules in `BatchAccountingService`;
- canonical relation writes in `WorkbenchRelationCommandService`;
- pair relation persist, lifecycle event and read model persist behind explicit injected callbacks.

## Contract

### Inputs

- `submit(payload, session=...)`
  - `year`, `bank_year`, `oa_year`
  - `bank_row_id`
  - `oa_row_ids`
  - `actor`
  - `note`
  - `expected_version`
- `withdraw(relation_id, payload, session=...)`
  - route `relation_id`
  - `actor`
  - `reason` or `note`
  - `expected_version`

### Outputs

- Success remains HTTP `200` with the service result plus `affected_months`.
- `batch_accounting_version_conflict` remains HTTP `409`.
- Other `BatchAccountingError` values remain HTTP `400`.
- Invalid submit DTO coercion remains `invalid_batch_accounting_request` HTTP `400`.
- Withdraw `KeyError` remains HTTP `400` with the previous error payload shape.
- Submit pair relation persist failure still returns HTTP `503` with `workbench_state_persistence_unavailable`.

### State And Events

- `BatchAccountingService.submit(...)` and `BatchAccountingService.withdraw(...)` remain the mutation state transition owners.
- `BatchAccountingApiRoutes` computes changed scope keys from mutation results through injected `scope_keys_for_row_ids`.
- Write-after effects remain:
  - `_schedule_workbench_pair_relation_persist(...)`
  - `_execute_derived_data_lifecycle_event("batch_accounting_relation_changed", ...)`
  - `_schedule_workbench_read_model_persist(...)`
- Submit persist failure still restores the previous pair relation snapshot and reconfigures the Workbench exception application service through an injected restore callback.

### Read Model

- This slice does not change `workbench_relation` read model semantics.
- Submit/withdraw still rely on the existing service/read facade/command safety checks.
- Write success still schedules `batch_accounting_relation_changed` and Workbench read model persist for affected scopes.

### Permissions

- `server.py` still resolves `_batch_accounting_mutation_session(...)` before invoking the route owner.
- The route owner receives a validated `OARequestSession` and only uses it for actor fallback.

### Legacy Retirement / Quarantine

| Legacy path | Current caller | Target state | Evidence |
| --- | --- | --- | --- |
| Inline submit DTO/service/side-effect body in `server.py` | `_handle_api_batch_accounting_submit` | removed from server handler | handler now delegates to `_batch_accounting_routes().submit(...)`; static guard checks route owner owns service call |
| Inline withdraw DTO/service/side-effect body in `server.py` | `_handle_api_batch_accounting_withdraw` | removed from server handler | handler now delegates to `_batch_accounting_routes().withdraw(...)`; static guard checks route owner owns service call |
| Direct relation command/pair writes from route owner | none allowed | forbidden | static guard checks route owner does not call `confirm_relation`, `withdraw_relation`, pair direct write fallbacks or history writes |
| `_repair_batch_accounting_relation_case_ids` | explicit compat repair helper | still open compat/quarantine gap | queued as next boundary |

## Impact Analysis

### Backend

| Layer | Impact | Risk | Evidence |
| --- | --- | --- | --- |
| route / HTTP mapping | yes | server wrapper might lose auth/session/JSON behavior | static guard; API tests |
| application route owner | yes | side effects could move behind unclear dependencies | explicit constructor callbacks |
| service | no behavior change | service call arguments could change | API/service regression tests |
| repository / SQL | no | none | not applicable |
| audit / permission | no semantic change | actor fallback or permission gate could regress | API tests and session guard |

### Read Model / Worker

No read model key, scope policy, queue, worker or freshness definition changes. The route owner still schedules existing Workbench relation lifecycle/read-model persist callbacks after successful mutation.

### Frontend

No API shape, route path, response field or frontend behavior changed. Existing operation overlay semantics remain driven by the same success payload and affected scopes.

## State Machine Impact

- Global workflow definition: unchanged.
- Reviewed global state file: `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`.
- Module state definition: unchanged.
- Reviewed module state file: `docs/modules/batch-accounting/state-machine.md`.
- Reason: this slice changes route ownership and side-effect orchestration location only; it does not add, remove or rename business, UI, read model, worker, operation barrier, force-refresh, permission or legacy-retirement state definitions.
- Progress/accounting files must still be updated: `autonomous/STATE.md`, `autonomous/MODULE-QUEUE.md`, `autonomous/JOURNAL.md`, `autonomous/NEXT-PROMPT.md`.

## Seven Test Categories

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | applicable through regression | Batch accounting API tests cover amount mismatch, valid submit, withdraw reason and non-fresh relation behavior; no business rule changed. |
| 2. Service-layer tests | applicable | Existing service tests still prove submit/withdraw delegate to command service and fail fast without direct pair fallback. |
| 3. API contract tests | applicable | Targeted API tests cover submit/withdraw status and error payloads after route owner extraction. |
| 4. Read model/cache/background job tests | applicable through regression | Mutation success still schedules existing Workbench relation lifecycle/read model callbacks; no worker contract changed. |
| 5. Frontend component and interaction tests | not changed in this slice | No frontend files, API shape or visible state changed. |
| 6. End-to-end business-flow integration tests | covered by API integration-style tests for this slice | Full browser flow remains unchanged and is not rerun for this backend route-owner extraction. |
| 7. Existing feature regression tests | applicable | Static route boundary guard plus submit/withdraw API regressions protect old behavior. |

## Verification

Targeted verification already executed before documentation:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_amount_mismatch_requires_difference_note tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_amount_mismatch_rejects_whitespace_note tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_creates_batch_accounting_relation_with_current_invoice_rows tests.test_batch_accounting_api.BatchAccountingApiTests.test_withdraw_requires_reason_and_batch_accounting_relation tests.test_batch_accounting_api.BatchAccountingApiTests.test_withdraw_rejects_when_relation_read_model_is_not_fresh -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_rolls_back_relation_when_pair_relation_persist_scheduling_fails -v`

Final verification must also run app check, docs check and diff check before commit.

