# Runtime Workers Workbench Matching Orchestrator Constructor Fix 2026-06-25

**Boundary:** `runtime-workers:workbench-matching-orchestrator-constructor-fix`
**Final status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Controller:** T0
**Base commit:** `d6583295c9f15c7ee78ddc7b713986b5cf6cf6d5`

## Trigger Evidence

`production:post-convergence-readiness-worker-db-aggregate-evidence-sweep` proved active dirty scopes and App Status readiness are clean, but `fin-ops-worker@workbench-matching.service` is in a systemd restart loop. The worker log traceback is:

```text
TypeError: WorkbenchMatchingOrchestrator.__init__() got an unexpected keyword argument 'pair_relation_service'
```

The traceback points to deployed `backend/src/fin_ops_platform/services/runtime_worker_handlers.py` inside `WorkbenchMatchingWorkerFactory.build_dirty_scope_worker(...)`.

## Scope

- Fix the local runtime worker factory wiring for `WorkbenchMatchingOrchestrator`.
- Preserve existing `WorkbenchPairRelationService` snapshot loading and command-service wiring.
- Add a focused regression guard preventing stale `pair_relation_service=` from being passed to the orchestrator.
- Update runtime worker module implementation/testing notes.

Out of scope:

- Deploy, restart, requeue, worker replay, resolve, repair or readiness mutation.
- Broad cleanup of historical `dead_lettered` rows.
- Go/Fiber/Go Worker admission or implementation.

## CodeGraph Context

CodeGraph confirmed:

- `WorkbenchMatchingOrchestrator.__init__(...)` requires `relation_read_port: WorkbenchMatchingRelationReadPort`.
- `WorkbenchMatchingRelationReadPort` wraps a relation reader and requires `list_active_relations()` plus `active_relations_for_row_ids(...)`.
- `WorkbenchPairRelationService` already provides those read methods and remains the correct snapshot-backed reader for the runtime worker factory.

## Implementation Plan

1. Import `WorkbenchMatchingRelationReadPort` in `runtime_worker_handlers.py`.
2. Change the orchestrator construction from stale `pair_relation_service=pair_relation_service` to `relation_read_port=WorkbenchMatchingRelationReadPort(pair_relation_service)`.
3. Extend `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_workbench_matching_uses_relation_read_port_not_pair_service` so it also covers `WorkbenchMatchingWorkerFactory`.
4. Run targeted unit/static verification, docs verification and diff checks.

## Docs Impact Assessment

- `docs/modules/runtime-workers/README.md`: no change needed; current boundary already states workers must keep explicit module boundaries and avoid Application/HTTP dependencies.
- `docs/modules/runtime-workers/state-machine.md`: no state definition change; queue/outbox/dirty/readiness states and allowed transitions are unchanged.
- `docs/modules/runtime-workers/implementation-notes.md`: update required because this is a production worker startup regression fix.
- `docs/modules/runtime-workers/tests.md`: update required because the regression belongs in the runtime worker historical bug library.

## Seven Test Categories

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rule, amount calculation, state transition, classification, permission or idempotency rule changes. |
| 2. Service-layer tests | Applicable | Runtime worker factory wiring is service-layer/background orchestration; add a static regression guard and run targeted worker/orchestrator tests. |
| 3. API contract tests | Not applicable | No HTTP route or response shape changes. |
| 4. Read model/cache/background job tests | Applicable | Workbench matching worker startup affects background read-model matching work; guard the constructor contract and run Workbench matching tests. |
| 5. Frontend component and interaction tests | Not applicable | No frontend UI or page behavior changes. |
| 6. End-to-end business-flow integration tests | Deferred | The local slice fixes constructor wiring only; production deploy/restart/convergence requires a separate bounded runbook after commit. |
| 7. Existing feature regression tests | Applicable | Existing Workbench matching suppression/decision tests and runtime boundary guards protect old behavior and the constructor contract. |

## Implementation Result

- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py` now imports `WorkbenchMatchingRelationReadPort`.
- `WorkbenchMatchingWorkerFactory.build_dirty_scope_worker(...)` now passes `relation_read_port=WorkbenchMatchingRelationReadPort(pair_relation_service)` to `WorkbenchMatchingOrchestrator(...)`.
- Existing `pair_relation_service` snapshot loading and relation command service wiring are unchanged.
- `tests/test_platform_runtime_boundary_guards.py::PlatformRuntimeBoundaryGuardTests.test_workbench_matching_uses_relation_read_port_not_pair_service` now also guards the runtime worker factory construction path.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_matching_uses_relation_read_port_not_pair_service -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_matching_orchestrator -v`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Remaining Risk

Local tests prove the constructor contract and existing Workbench matching behavior, but they do not start the production systemd unit. Production convergence remains deferred to a separate controlled deploy/restart/check boundary: `production:workbench-matching-constructor-fix-deploy-and-convergence-runbook`.
