# Workbench Relation Pair Relation Persist Schedule Helper Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:pair-relation-persist-schedule-helper-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Select a narrow persist/schedule extraction next:

`workbench-relations:pair-relation-persist-service-extraction`

The next slice should extract non-transactional pair relation persistence and scheduling from `server.py` into an explicit service, while leaving rollback restore and broader relation lifecycle migration for later.

## Evidence

Remaining app helpers:

- `_persist_workbench_pair_relations(...)`
- `_schedule_workbench_pair_relation_persist(...)`
- `_workbench_pair_relation_persist_async_enabled(...)`
- `_persist_workbench_pair_relations_in_background(...)`
- `_restore_workbench_pair_relation_snapshot(...)`

CodeGraph and text search show:

- `_schedule_workbench_pair_relation_persist(...)` is used by Workbench exception/batch accounting compatibility paths and by `WorkbenchWriteFacade` callback wiring.
- `_persist_workbench_pair_relations_in_background(...)` is only called by the scheduler and tests.
- `_persist_workbench_pair_relations(...)` has direct callers from ETC/input invoice/auto pair/repair flows and from background persist.
- `_restore_workbench_pair_relation_snapshot(...)` is used by `WorkbenchWriteFacade` rollback paths through callback injection.

## Boundary Selection

The next implementation should extract these cohesive non-transactional persist/schedule behaviors:

- direct persist;
- scheduler state and coalescing;
- async env toggle;
- background persist and timing emission.

Suggested service:

- file: `backend/src/fin_ops_platform/services/workbench_pair_relation_persist_service.py`
- class: `WorkbenchPairRelationPersistService`

Suggested dependencies:

- `pair_relation_service`;
- `state_store`;
- `clear_search_cache`;
- `emit_action_timing`;
- `duration_ms`;
- `thread_factory` or default `Thread`;
- `monotonic_clock` for tests.

Do not include `_restore_workbench_pair_relation_snapshot(...)` in that slice. It is rollback-oriented and should be handled separately after schedule/persist extraction.

## Remaining Gaps After Next Slice

- Rollback restore snapshot helper remains app-owned.
- WorkbenchWriteFacade still receives relation callbacks, but callbacks should point to the explicit persist service for persist/schedule.
- Broader relation lifecycle migration remains open.
- Production PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

## Legacy Path Classification

- `_persist_workbench_pair_relations(...)`: implementation-pending.
- `_schedule_workbench_pair_relation_persist(...)`: implementation-pending.
- `_workbench_pair_relation_persist_async_enabled(...)`: implementation-pending.
- `_persist_workbench_pair_relations_in_background(...)`: implementation-pending.
- `_restore_workbench_pair_relation_snapshot(...)`: implementation-pending but excluded from the next slice to keep scope bounded.
- Blocked-by-human-gate: none.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No state definition changes are needed. This audit closes as `analysis-closed`; `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No business rules changed. |
| Service-layer tests | Not applicable for this audit. The next implementation should add persist service tests. |
| API contract tests | Not applicable. No HTTP behavior changed. |
| Read model/cache/background job tests | Not applicable. No runtime behavior changed in this audit. |
| Frontend component and interaction tests | Not applicable. |
| End-to-end business-flow integration tests | Not applicable. |
| Existing feature regression tests | Applicable through docs/diff verification and CodeGraph evidence review. |

## Verification

Pending before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Completion Claim

This slice closes only the persist/schedule helper audit. It does not extract code, close `workbench_relation`, validate production evidence or unblock Go admission.
