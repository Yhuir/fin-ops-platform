# Workbench Relation Pair Relation Persist Service Extraction

**Date:** 2026-06-24
**Boundary:** `workbench-relations:pair-relation-persist-service-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`server.py` still owned the non-transactional pair relation persist/schedule/background helper group:

- `_persist_workbench_pair_relations(...)`
- `_schedule_workbench_pair_relation_persist(...)`
- `_workbench_pair_relation_persist_async_enabled(...)`
- `_persist_workbench_pair_relations_in_background(...)`

The previous audit explicitly excluded `_restore_workbench_pair_relation_snapshot(...)` because rollback restore has different semantics and should not be bundled with ordinary persist/schedule behavior.

## Selected Boundary

Extract non-transactional pair relation persistence and scheduling into:

- `backend/src/fin_ops_platform/services/workbench_pair_relation_persist_service.py`
- `WorkbenchPairRelationPersistService`

## Transition Guard

Allowed:

- Move direct persist, changed-case snapshot selection, search cache clearing, scheduler coalescing, async env toggle, background stale-version skip and timing emission into the service.
- Keep temporary `Application` wrapper methods for existing callbacks/tests while making them delegates only.
- Preserve `Thread` patchability through dependency injection.

Forbidden:

- Do not change transaction-bound persistence.
- Do not include `_restore_workbench_pair_relation_snapshot(...)`.
- Do not change relation business rules, API payloads, dirty scope semantics, permissions, audit meaning or production state.
- Do not implement Go/Fiber/Go Worker.

## Implementation Evidence

- Added `WorkbenchPairRelationPersistService`.
- `Application._persist_workbench_pair_relations(...)` delegates to `service.persist(...)`.
- `Application._schedule_workbench_pair_relation_persist(...)` delegates to `service.schedule(...)`.
- `Application._persist_workbench_pair_relations_in_background(...)` delegates to `service.persist_in_background(...)`.
- `Application._workbench_pair_relation_persist_async_enabled()` delegates to `WorkbenchPairRelationPersistService.async_enabled_from_env()`.
- App-level pair relation persist compatibility state is mirrored from the service for existing tests/callers that inspect `_workbench_pair_relation_persist_version` and `_pending_workbench_pair_relation_case_ids`.
- Removed the unused app-level `_workbench_pair_relation_persist_version_lock`.
- Added static guard coverage proving `server.py` no longer owns `save_workbench_pair_relations(...)`, pending case coalescing, thread creation or timing emission inside those wrappers.

## Legacy Path Classification

- `_persist_workbench_pair_relations(...)`: compat-only delegate retained for existing callback wiring.
- `_schedule_workbench_pair_relation_persist(...)`: compat-only delegate retained for existing callback wiring.
- `_workbench_pair_relation_persist_async_enabled(...)`: compat-only delegate retained for tests/env contract.
- `_persist_workbench_pair_relations_in_background(...)`: compat-only delegate retained for existing thread callback/tests.
- `_restore_workbench_pair_relation_snapshot(...)`: implementation-gap-open and excluded from this slice.

Compat-only wrappers must not write canonical facts, dirty scopes, outbox events, read model readiness, cache or App Status directly. They may only delegate to the explicit service boundary.

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
| Service-layer tests | Applicable. Added `tests/test_workbench_pair_relation_persist_service.py` for persist, schedule, coalescing and timing behavior. |
| API contract tests | Not applicable. No HTTP route or response shape changed. |
| Read model/cache/background job tests | Applicable. Existing scheduler/background tests plus the new service tests cover cache clear, changed-case persistence, async stale-version skip, sync persist and timing emission. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not added for this narrow service extraction; existing Workbench write characterization and UoW tests cover cross-service write behavior without changing API/UI. |
| Existing feature regression tests | Applicable. Existing scheduler, background timing, Workbench write characterization and UoW tests were run. |

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_pair_relation_persist_service -v
PYTHONPATH=backend/src python3 -m pytest tests/test_workbench_persist_scheduler.py -q
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_pair_relation_persist_uses_explicit_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_background_persist_emits_timing_logs -v
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

This slice closes only the non-transactional pair relation persist service extraction. It does not close `workbench_relation`, does not migrate rollback restore, does not validate production PostgreSQL/worker/App Status/high-row/browser evidence, and does not unblock Go admission.

## Next Boundary

`workbench-relations:restore-pair-relation-snapshot-helper-audit`
