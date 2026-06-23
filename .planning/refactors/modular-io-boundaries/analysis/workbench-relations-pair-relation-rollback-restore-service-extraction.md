# Workbench Relation Pair Relation Rollback Restore Service Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:pair-relation-rollback-restore-service-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`Application._restore_workbench_pair_relation_snapshot(...)` owned rollback restore behavior for WorkbenchWriteFacade confirm/cancel/withdraw failure paths.

## Selected Boundary

Extract pair relation snapshot rollback restore behavior into:

- `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
- `WorkbenchPairRelationRollbackRestoreService`

## Transition Guard

Allowed:

- Move pair relation snapshot rehydrate, exception application service reconfigure and state store best-effort rollback save into the service.
- Keep `Application._restore_workbench_pair_relation_snapshot(...)` as a compat-only delegate for WorkbenchWriteFacade callback wiring.
- Ensure all app-level pair relation service replacement paths clear the cached pair relation persist service so future persists do not point at a stale service object.

Forbidden:

- Do not change relation business rules, API shape, dirty scope semantics, permissions, audit meaning or production state.
- Do not migrate broader exception restore helpers except for the narrow cache invalidation needed after pair relation service replacement.
- Do not implement Go/Fiber/Go Worker.

## Implementation Evidence

- Added `WorkbenchPairRelationRollbackRestoreService`.
- `Application._restore_workbench_pair_relation_snapshot(...)` delegates to `service.restore(...)`.
- Added `Application._replace_workbench_pair_relation_service(...)` to centralize pair relation service replacement and clear `_workbench_pair_relation_persist_service_instance`.
- Existing exception and batch-accounting restore helpers now use `_replace_workbench_pair_relation_service(...)` when replacing the pair relation service, preserving their existing restore semantics while keeping the new persist service cache consistent.
- Added service tests and static guard coverage.

## Legacy Path Classification

- `_restore_workbench_pair_relation_snapshot(...)`: compat-only delegate retained for `WorkbenchWriteFacade`.
- `_restore_workbench_exception_pair_snapshots(...)`: implementation-gap-open; uses the centralized replacement helper but still owns exception+pair rollback orchestration.
- `_restore_workbench_exception_write_snapshots(...)`: implementation-gap-open; uses the centralized replacement helper but still owns exception/candidate/override/pair rollback orchestration.
- `_restore_batch_accounting_pair_relation_snapshot(...)`: compat-only route-local rollback helper; now uses centralized replacement helper.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No global or module state definition changed. This slice transitions to `implementation-closed`; `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. Relation business rules and state transitions were not changed. |
| Service-layer tests | Applicable. Added `tests/test_workbench_pair_relation_rollback_restore_service.py` for restore, reconfigure and best-effort save behavior. |
| API contract tests | Not applicable. No HTTP route or response shape changed. |
| Read model/cache/background job tests | Applicable through rollback cache consistency: static guard proves pair relation service replacement clears cached persist service; Workbench write characterization verifies rollback paths. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not added for this narrow internal rollback extraction; existing Workbench write/UoW regression coverage protects the affected flows. |
| Existing feature regression tests | Applicable. Workbench write characterization, UoW and app check were run. |

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_rollback_restore_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_pair_relation_restore_uses_explicit_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_read_model_scheduling_failure_propagates_after_pair_relation_fact_is_mutated tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_withdraw_link_read_model_scheduling_failure_rolls_back_relation_withdraw tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cancel_link_uow_outbox_failure_restores_relation -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_uow_contract -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

Pending for final pre-commit verification:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the pair relation rollback restore service extraction. It does not close `workbench_relation`, does not migrate exception restore orchestration helpers, does not validate production evidence and does not unblock Go admission.

## Next Boundary

`workbench-relations:exception-restore-helper-audit`
