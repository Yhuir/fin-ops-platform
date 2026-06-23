# Workbench Relations - Whole-State Persistence Closure Accounting Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:whole-state-persistence-closure-accounting-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit full-state persistence, bootstrap and compatibility snapshot paths for Workbench relation facts after persist and rollback accounting, without changing runtime behavior in this audit slice.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-rollback-closure-accounting-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-transaction-persist-closure-accounting-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`
- `tests/test_app_postgres_mode.py`
- `tests/test_postgres_state_store.py`
- `tests/test_state_store.py`
- `tests/test_state_store_contract.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Whole-State Surface Accounting

| Surface | Classification | Evidence | Closure Decision |
| --- | --- | --- | --- |
| App bootstrap `WorkbenchPairRelationService.from_snapshot(...)` | accepted bootstrap compatibility | App startup loads relation facts through `_runtime_repository_snapshot(..., "workbench_pair_relations", "load_workbench_pair_relations")`; `tests/test_app_postgres_mode.py` verifies Postgres mode uses the domain runtime loader and does not call full snapshot load. | Accept as bootstrap assembly while in-memory domain service still exists. Not a page read/write path. |
| `PostgresStateStore.load_workbench_pair_relations(...)` | accepted compatibility/domain loader | Loads from `PostgresWorkbenchRelationRepository` and normalizes with fallback snapshot only when present. | Accept as domain loader. |
| `PostgresStateStore.save_workbench_pair_relations(...)` | implemented repository delegate with fallback snapshot | Delegates to `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` then stores a fallback snapshot. | Accept as compatibility method for relation-specific saves. |
| `PostgresStateStore.save(...)` full-state branch for `workbench_pair_relations` | implementation gap | `save(...)` calls `save_workbench_pair_relations(...)` whenever the broad payload contains `workbench_pair_relations`. This is acceptable only if callers avoid including relation facts for unrelated full-state saves. |
| `ApplicationStateStore.load/save_workbench_pair_relations(...)` | accepted local/Mongo compatibility | Mongo/local store keeps detailed relation collections and changed-case incremental saves. Tests cover round trip, incremental changed-case update, and no unrelated collection rewrites. | Accept for non-Postgres/local compatibility. |
| `Application._persist_state(...)` | next implementation boundary | Always includes `"workbench_pair_relations": self._workbench_pair_relation_service.snapshot()` in broad full-state payload. `_persist_state(...)` is called by many unrelated import/settings/cache paths, so this old whole-state path can touch relation persistence and refresh boundaries even when the current operation did not change relations. | Must be quarantined before local closure/defer. |
| `_persist_state_with_workbench_invalidation(...)` | depends on `_persist_state(...)` | Invalidates read models and then calls `_persist_state(...)`; relation snapshot inclusion therefore propagates into import-state persistence. | Covered by the same next implementation boundary. |

## Decision

Do not mark `workbench_relation` closed.

Do not run Go admission.

Do not treat whole-state persistence as fully accounted for yet.

Queue a narrow implementation boundary:

`workbench-relations:persist-state-relation-snapshot-quarantine`

Expected implementation direction:

- Stop `Application._persist_state(...)` from including `workbench_pair_relations` in broad full-state payloads.
- Keep relation-specific persistence through `_persist_workbench_pair_relations(...)`, `_schedule_workbench_pair_relation_persist(...)`, `_persist_workbench_pair_relations_in_transaction(...)`, command repository save paths and state-store domain methods.
- Preserve app bootstrap loading through `load_workbench_pair_relations`.
- Preserve local/Mongo relation domain save/load contract.
- Add or update a static/runtime guard proving broad `_persist_state(...)` no longer serializes relation snapshot facts.
- Run targeted app/postgres mode and state-store regression tests.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:whole-state-persistence-closure-accounting-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:persist-state-relation-snapshot-quarantine`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business behavior changed.
2. Service-layer tests: existing state-store and Postgres mode tests were reviewed; no code changed in this audit.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: not added in this audit; the next implementation slice must protect relation refresh boundaries from broad state saves.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not applicable for this analysis-only slice.
7. Existing feature regression tests: not run because this slice only records closure accounting.

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this audit slice is closed. `workbench_relation` remains `implementation-gap-open`, and a concrete implementation gap is queued next.
