# Batch Accounting Repair Compat Removal

**Date:** 2026-06-24
**Boundary:** `batch-accounting:repair-compat-quarantine`
**Status:** implementation slice closed; module closure audit still pending

## Previous State

- `BatchAccountingService.repair_legacy_case_id_collisions(...)` is the service-level historical repair capability.
- `Application._repair_batch_accounting_relation_case_ids(...)` was an app-level wrapper that called the service repair, scheduled pair relation persist, emitted `batch_accounting_relation_changed`, and scheduled Workbench read model persist.
- Prior docs classified the app-level helper as explicit compat repair, but it had no route or runtime caller.

## Evidence

CodeGraph:

- `codegraph_search("_repair_batch_accounting_relation_case_ids")` found exactly one method definition in `server.py`.
- `codegraph_callers("_repair_batch_accounting_relation_case_ids")` found no callers.
- `rg "_repair_batch_accounting_relation_case_ids|repair_batch_accounting_relation_case_ids"` found only:
  - the old method definition;
  - planning/docs/tests references;
  - no runtime caller.

## Decision

Remove `Application._repair_batch_accounting_relation_case_ids(...)` instead of quarantining it.

Reason:

- No runtime caller exists.
- Keeping the wrapper would preserve an app-level path that can write pair relation persistence, lifecycle events and read model persist outside the normal route owner boundary.
- The service-level repair capability remains covered by tests and command-service boundary guards.

## Contract

### Inputs / Outputs

No public API input or output changes. The removed helper was private and unused.

### State And Events

No business/UI/read model/worker state definition changes.

The removed wrapper can no longer emit:

- `_schedule_workbench_pair_relation_persist(..., action_name="repair_batch_accounting_relation_case_ids")`
- `_execute_derived_data_lifecycle_event("batch_accounting_relation_changed", ...)`
- `_schedule_workbench_read_model_persist(..., action_name="repair_batch_accounting_relation_case_ids")`

Because it had no callers, this removes dead legacy write capability without changing live behavior.

### Canonical Facts

Canonical relation repair remains owned by `BatchAccountingService.repair_legacy_case_id_collisions(...)` and `WorkbenchRelationCommandService.confirm_relation(...)`.

### Legacy Retirement

| Legacy path | Caller evidence | Target state | Proof |
| --- | --- | --- | --- |
| `Application._repair_batch_accounting_relation_case_ids(...)` | CodeGraph no callers; rg no runtime caller | removed | method deleted; static guard fails if it returns |
| `BatchAccountingService.repair_legacy_case_id_collisions(...)` | service tests only / explicit repair service capability | retained service-level repair capability | existing API/service tests prove command-service delegation and no direct pair write fallback |

## State Machine Impact

- Global workflow definition: unchanged.
- Reviewed global state file: `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`.
- Module state definition: unchanged.
- Reviewed module state file: `docs/modules/batch-accounting/state-machine.md`.
- Reason: this slice removes an unused private app helper. It does not add, remove or rename business, UI, read model, worker, operation barrier, force-refresh or permission states.

## Seven Test Categories

| Category | Applicability | Evidence |
| --- | --- | --- |
| 1. Business core unit tests | service repair behavior applicable | Existing repair tests still cover command-service repair semantics. |
| 2. Service-layer tests | applicable | `test_repair_legacy_case_id_collision_*` continue proving service-level repair behavior and fail-fast without command service. |
| 3. API contract tests | applicable as regression | `test_unsubmitted_list_does_not_run_legacy_relation_repair` now proves the app helper is absent and GET still returns expected rows. |
| 4. Read model/cache/background job tests | applicable as boundary guard | Removing the helper prevents an unused app-level path from scheduling lifecycle/read model persist; no worker contract changed. |
| 5. Frontend component and interaction tests | not applicable | No frontend behavior, route path or API shape changed. |
| 6. End-to-end business-flow integration tests | not applicable for this private-helper removal | Live submit/withdraw/list flows are unchanged; service repair remains unit/API covered. |
| 7. Existing feature regression tests | applicable | Static guard plus batch accounting repair/list tests protect against legacy helper reintroduction and service repair regression. |

## Verification

Targeted verification already executed:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_route_handlers_do_not_bypass_service_boundaries tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_repair_has_no_direct_pair_write_fallback -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_unsubmitted_list_does_not_run_legacy_relation_repair tests.test_batch_accounting_api.BatchAccountingApiTests.test_repair_legacy_case_id_collision_delegates_relation_write_to_command_service tests.test_batch_accounting_api.BatchAccountingApiTests.test_repair_legacy_case_id_collision_requires_relation_command_service_without_direct_pair_fallback tests.test_batch_accounting_api.BatchAccountingApiTests.test_repair_legacy_case_id_collision_restores_lost_batch_relation_from_history -v`

Final verification must also run app check, docs check and diff check before commit.

