# Workbench Relation Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:workbench-relation-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Do not mark `workbench_relation` closed and do not start Go admission.

The repository port and derived lifecycle executor support slices are locally complete, but the module still has implementation gaps around relation write lifecycle, relation SQL ownership, Application-owned snapshot/persist helpers, and production evidence.

The next narrow implementation boundary should be:

`workbench-relations:transaction-persist-repository-owner-split`

This is narrower than a full command-service migration. It should replace the transaction helper's broad `PostgresWorkbenchRepository(...).save_workbench_pair_relations(...)` usage with the existing relation-specific `PostgresWorkbenchRelationRepository(...).save_workbench_pair_relations(...)`, preserving behavior and tests.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-workbench-relation-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-workbench-relation-derived-lifecycle-executor-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph lookup for `_persist_workbench_pair_relations`, `_workbench_relation_command_repository`, callers and related relation command paths.

## Local Evidence Already Closed

- `WorkbenchRelationReadModelRepositoryPort` exists and is wired into app/worker/projection builder relation read-model paths.
- `WorkbenchRelationDerivedLifecycleExecutor` owns derived lifecycle refresh enqueue payload behavior.
- `WorkbenchRelationReadFacade` remains the downstream relation distribution read boundary.
- Static guards already prevent several downstream services and legacy repair paths from accepting direct pair write fallbacks.
- `PostgresWorkbenchRelationRepository` already exists and owns relation-specific SQL implementation for `load_workbench_pair_relations` / `save_workbench_pair_relations`.

## Remaining Local Gaps

### 1. Transaction Persist Still Uses Broad Workbench Repository

`Application._persist_workbench_pair_relations_in_transaction(...)` still calls:

```python
PostgresWorkbenchRepository(transaction).save_workbench_pair_relations(...)
```

This contradicts the target owner split in `docs/modules/workbench-relations/README.md`, which says relation SQL belongs to `PostgresWorkbenchRelationRepository`.

This is the smallest next implementation boundary because the relation-specific repository already exposes the required method.

### 2. App-Level Command Repository Adapter Still Owns Snapshot Apply Logic

`server.py` still owns:

- `_workbench_relation_command_repository(...)`
- `_save_workbench_relation_command_snapshot(...)`
- `_apply_workbench_relation_command_snapshot(...)`
- `_relation_history_touches_cases(...)`

These are not closed. They are currently dependency assembly plus in-memory snapshot merge logic, but they should be audited after the transaction repository owner split.

### 3. App-Level Pair Relation Persist Helpers Remain

`server.py` still owns:

- `_persist_workbench_pair_relations(...)`
- `_persist_workbench_pair_relations_in_transaction(...)`
- `_schedule_workbench_pair_relation_persist(...)`
- `_persist_workbench_pair_relations_in_background(...)`
- `_restore_workbench_pair_relation_snapshot(...)`

Some callers are still active relation write or repair flows. These helpers cannot be deleted in one broad slice.

### 4. WorkbenchWriteFacade Still Receives Relation Snapshot/Persist Callbacks

`Application._workbench_write_facade(...)` still injects `pair_relation_service`, relation persist callbacks and relation command service factory. This is a known local implementation gap, but it is broader than the next slice.

### 5. Production Evidence Remains Deferred

There is no local `PGSQL_URL` or staging database. Real PostgreSQL dirty/outbox/readiness, worker drain, App Status, high-row replay and browser evidence must remain deferred unless a future slice performs approved read-only production checks.

## Legacy Path Classification

- Removed in prior slices: app-level workbench relation read-model repository broad dependency and app-level derived lifecycle executor.
- Retained as implementation-pending: transaction persist through broad `PostgresWorkbenchRepository`.
- Retained as implementation-pending: app-level command repository snapshot/apply helpers.
- Retained as implementation-pending: app-level pair relation persist/schedule/background helpers.
- Compat-only/quarantined: existing static guards classify many downstream direct pair write fallbacks as forbidden; this audit does not change those classifications.
- Blocked-by-human-gate: none for the next local implementation boundary.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `docs/modules/workbench-relations/state-machine.md`

No state definition changes are needed. This audit only selects the next implementation boundary and keeps `workbench_relation` as `implementation-gap-open`.

Success transition:

- `read-models:workbench-relation-local-implementation-closure-audit` -> `analysis-closed`
- next boundary -> `workbench-relations:transaction-persist-repository-owner-split`

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. This audit changes no business rules. |
| Service-layer tests | Not applicable for this audit. The next implementation slice should run relation repository/command service tests. |
| API contract tests | Not applicable. No HTTP behavior changes. |
| Read model/cache/background job tests | Not applicable for this audit. The next slice should protect transaction enqueue/fan-out behavior. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changes. |
| End-to-end business-flow integration tests | Not applicable. No runtime behavior changes. |
| Existing feature regression tests | Applicable through docs/diff verification and current static evidence review; no tests are changed in this audit. |

## Verification

Pending before commit:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Completion Claim

This audit closes only the local implementation closure audit slice. It does not close `workbench_relation`, does not migrate relation lifecycle, does not validate production PostgreSQL/worker/App Status/high-row/browser behavior, and does not unblock Go admission.
