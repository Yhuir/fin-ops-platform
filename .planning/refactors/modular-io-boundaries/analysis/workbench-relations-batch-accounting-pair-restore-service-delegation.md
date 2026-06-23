# Workbench Relations Batch Accounting Pair Restore Service Delegation

**Date:** 2026-06-24
**Boundary:** `workbench-relations:batch-accounting-pair-restore-service-delegation`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Make the batch-accounting pair relation restore callback reuse the explicit rollback restore service boundary instead of letting `server.py` directly rehydrate `WorkbenchPairRelationService` from a snapshot.

## Changes

- `Application._restore_batch_accounting_pair_relation_snapshot(...)` now delegates to `WorkbenchPairRelationRollbackRestoreService.restore(...)`.
- Added `Application._batch_accounting_pair_relation_rollback_restore_service(...)` as dependency assembly for the route-local rollback callback.
- The batch-accounting rollback restore service is constructed with `state_store=None`, preserving the existing behavior that this route-local rollback restores in-memory state and reconfigures exception application service without saving a rollback snapshot.
- Added a static boundary guard proving the batch-accounting wrapper:
  - delegates to `.restore(...)`;
  - passes `changed_case_ids=[]`;
  - does not call `WorkbenchPairRelationService.from_snapshot(...)`;
  - does not directly call `_configure_workbench_exception_application_service()`;
  - does not call `save_workbench_pair_relations(...)`;
  - uses shared pair service replacement so cached persist service state is cleared.

## Preserved Behavior

- `BatchAccountingApiRoutes` still owns submit/withdraw DTO and route-side orchestration.
- The route callback wiring remains intact.
- Submit persist scheduling failure still returns `503` with `workbench_state_persistence_unavailable`.
- Submit persist scheduling failure still restores the previous pair relation snapshot.
- No withdraw rollback behavior was added.
- No API payload shape, command service write semantics, dirty scope semantics or read model refresh behavior changed.

## Legacy Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `BatchAccountingApiRoutes._restore_pair_relation_snapshot` | compat-only route callback | Kept for route owner isolation and submit rollback injection. |
| `Application._restore_batch_accounting_pair_relation_snapshot(...)` | compat-only delegate | No longer owns direct restore behavior; delegates to rollback restore service. |
| `Application._batch_accounting_pair_relation_rollback_restore_service(...)` | dependency assembly | Builds `WorkbenchPairRelationRollbackRestoreService` with `state_store=None` for in-memory-only batch-accounting rollback. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This implementation closes one narrow app-owned restore helper gap. `workbench_relation` remains `implementation-gap-open`; the next safe boundary is another local closure audit before any production-evidence defer or Go admission decision.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. Business relation rules did not change. |
| Service-layer tests | Covered by existing `WorkbenchPairRelationRollbackRestoreService` service tests from the prior slice; this slice only changes app wiring. |
| API contract tests | Covered by `tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_rolls_back_relation_when_pair_relation_persist_scheduling_fails`, proving response shape and rollback behavior are unchanged. |
| Read model/cache/background job tests | Not applicable. No refresh, dirty scope, cache or worker behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this wiring-only slice; existing batch-accounting flow e2e remains the broader regression target. |
| Existing feature regression tests | Covered by the submit rollback API test and static runtime boundary guard. |

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_batch_accounting_api.BatchAccountingApiTests.test_submit_rolls_back_relation_when_pair_relation_persist_scheduling_fails -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_batch_accounting_pair_relation_restore_uses_explicit_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_pair_relation_restore_uses_explicit_service_boundary -v
```

Pending before commit:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the batch-accounting pair restore service delegation. It does not close `workbench_relation`, validate production evidence, or unblock Go admission.
