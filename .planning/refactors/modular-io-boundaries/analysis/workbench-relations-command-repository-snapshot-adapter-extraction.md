# Workbench Relation Command Repository Snapshot Adapter Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:command-repository-snapshot-adapter-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Decision

Extract the app-level relation command repository callback and snapshot merge/apply logic into an explicit adapter service.

This closes only the command repository snapshot adapter boundary. It does not remove broader pair relation persist/schedule/background helpers or migrate the whole relation lifecycle.

## Runtime Changes

- Added `backend/src/fin_ops_platform/services/workbench_relation_command_repository_adapter.py`.
- `Application._workbench_relation_command_repository(...)` now constructs `WorkbenchRelationCommandRepositoryAdapter`.
- Removed app-level helpers:
  - `_save_workbench_relation_command_snapshot(...)`
  - `_apply_workbench_relation_command_snapshot(...)`
  - `_relation_history_touches_cases(...)`
- Preserved `server.py` dependency assembly for:
  - runtime `WorkbenchPairRelationService`;
  - optional transaction repository;
  - post-apply `_configure_workbench_exception_application_service` callback.

## Preserved Behavior

- Command service still receives a repository exposing `load_workbench_pair_relations()` and `save_workbench_pair_relations(...)`.
- Snapshot load still reads the runtime pair relation mirror.
- Optional transaction repository save still happens before runtime mirror apply.
- Changed-case delta apply still replaces only touched cases.
- Untouched history remains preserved.
- History touching changed cases is replaced with incoming history.
- Runtime pair relation mirror internals are updated in place to preserve existing object references.
- Workbench exception application service wiring is refreshed after apply.

## Legacy Path Classification

- Removed: app-level save/apply/history helper methods.
- Retained as dependency assembly: `Application._workbench_relation_command_repository(...)`.
- Retained as implementation-pending: app-level pair relation persist/schedule/background helpers and WorkbenchWriteFacade callback wiring.
- Retained: `CallbackWorkbenchRelationRepository`, because tests and runtime worker handlers still use it independently.
- Blocked-by-human-gate: none.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No state definition changes are needed. Existing `implementation-closed` slice status and `implementation-gap-open` module closure are sufficient.

Next boundary:

`workbench-relations:pair-relation-persist-schedule-helper-audit`

That audit should classify `_persist_workbench_pair_relations(...)`, `_schedule_workbench_pair_relation_persist(...)`, `_persist_workbench_pair_relations_in_background(...)`, `_restore_workbench_pair_relation_snapshot(...)` and WorkbenchWriteFacade callback wiring before selecting the next implementation slice.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No relation mode/status/amount/idempotency rules changed. |
| Service-layer tests | Applicable. `tests/test_workbench_relation_command_repository_adapter.py` covers repository forwarding, changed-case merge, history replacement/preservation and post-apply callback behavior. |
| API contract tests | Not directly applicable. No HTTP route or response shape changed. |
| Read model/cache/background job tests | Applicable. Workbench UoW/write characterization tests protect transaction dirty/outbox and rollback behavior through the adapter. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this adapter extraction. |
| Existing feature regression tests | Applicable. Workbench relation command service, UoW/write characterization, static guard and app check protect existing relation write behavior. |

## Verification

Executed:

- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_command_repository_adapter -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_relation_command_repository_uses_explicit_snapshot_adapter tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_transaction_pair_relation_persist_uses_relation_repository_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_relation_command_service tests.test_workbench_uow_contract tests.test_workbench_write_characterization -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`

Pending before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Completion Claim

This slice closes only command repository snapshot adapter extraction. `workbench_relation` remains implementation-gap-open; pair relation persist/schedule/background helpers, broader relation lifecycle migration, production PostgreSQL/worker/App Status/high-row/browser evidence and Go admission remain open.
