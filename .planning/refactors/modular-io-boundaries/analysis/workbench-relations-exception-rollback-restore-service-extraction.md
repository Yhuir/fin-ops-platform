# Workbench Relation Exception Rollback Restore Service Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:exception-rollback-restore-service-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`server.py` still owned exception rollback restore orchestration through three helper methods and two inline restore blocks.

## Selected Boundary

Extract exception/pair/candidate/override rollback restore behavior into:

- `backend/src/fin_ops_platform/services/workbench_exception_rollback_restore_service.py`
- `WorkbenchExceptionRollbackRestoreService`

## Transition Guard

Allowed:

- Move exception case, pair relation, candidate match and override snapshot restoration into the service.
- Preserve best-effort `state_store.save_workbench_exception_cases(...)` behavior for exception/override rollback.
- Reuse the centralized pair relation replacement callback so cached pair relation persist service state remains consistent.
- Keep `server.py` wrappers for WorkbenchWriteFacade callback compatibility.

Forbidden:

- Do not change relation or exception business rules.
- Do not change API payloads, write semantics, dirty scope semantics, permissions, audit meaning or production state.
- Do not migrate unrelated batch-accounting restore behavior.
- Do not implement Go/Fiber/Go Worker.

## Implementation Evidence

- Added `WorkbenchExceptionRollbackRestoreService`.
- `_restore_workbench_exception_write_snapshots(...)` delegates to `restore_write_snapshots(...)`.
- `_restore_workbench_exception_pair_snapshots(...)` delegates to `restore_pair_snapshots(...)`.
- `_restore_workbench_exception_override_snapshots(...)` delegates to `restore_override_snapshots(...)`.
- `_apply_workbench_exception_application(...)` inline rollback now delegates to `restore_write_snapshots(...)`.
- `_persist_workbench_exception_and_override_change(...)` inline rollback now delegates to `restore_override_snapshots(...)`.
- Added service unit tests and static guard coverage for wrappers and inline restore paths.

## Legacy Path Classification

- `_restore_workbench_exception_write_snapshots(...)`: compat-only delegate retained for `WorkbenchWriteFacade`.
- `_restore_workbench_exception_pair_snapshots(...)`: compat-only delegate retained for `WorkbenchWriteFacade`.
- `_restore_workbench_exception_override_snapshots(...)`: compat-only delegate retained for `WorkbenchWriteFacade`.
- `_apply_workbench_exception_application(...)` inline restore: removed; now delegates to service.
- `_persist_workbench_exception_and_override_change(...)` inline restore: removed; now delegates to service.
- `_restore_batch_accounting_pair_relation_snapshot(...)`: out of scope.

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
| Business core unit tests | Not applicable. Relation/exception business rules were not changed. |
| Service-layer tests | Applicable. Added `tests/test_workbench_exception_rollback_restore_service.py` for write/pair/override restore methods. |
| API contract tests | Not applicable. No HTTP route or response shape changed. |
| Read model/cache/background job tests | Applicable through rollback consistency and existing Workbench write/UoW regression tests. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not added for this narrow internal rollback extraction; existing Workbench write/UoW regression coverage protects affected flows. |
| Existing feature regression tests | Applicable. Workbench write characterization, UoW and app check were run. |

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_exception_rollback_restore_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_exception_restore_uses_explicit_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_personal_advance_persistence_failure_rolls_back_exception_case_and_relation tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cash_special_scheduling_failure_propagates_after_metadata_mutation tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_update_bank_exception_scheduling_failure_propagates_after_case_and_override_are_persisted -v
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

This slice closes only the exception rollback restore service extraction. It does not close `workbench_relation`, does not validate production evidence and does not unblock Go admission.

## Next Boundary

`workbench-relations:post-restore-local-implementation-closure-audit`
