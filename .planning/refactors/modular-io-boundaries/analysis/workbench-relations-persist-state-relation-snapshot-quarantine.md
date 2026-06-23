# Workbench Relations - Persist State Relation Snapshot Quarantine

**Date:** 2026-06-24
**Boundary:** `workbench-relations:persist-state-relation-snapshot-quarantine`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove Workbench relation snapshot facts from broad app full-state persistence while preserving relation-specific save/load paths.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-whole-state-persistence-closure-accounting-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/state_store.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_app_postgres_mode.py`
- `tests/test_state_store_contract.py`
- `tests/test_postgres_state_store.py`

## Change Summary

- Removed `"workbench_pair_relations": self._workbench_pair_relation_service.snapshot()` from `Application._persist_state(...)`.
- Added a static boundary guard proving broad `_persist_state(...)` no longer:
  - serializes `"workbench_pair_relations"`
  - calls `_workbench_pair_relation_service.snapshot()`
  - directly calls `save_workbench_pair_relations(...)`
- Left relation-specific persistence paths unchanged:
  - `_persist_workbench_pair_relations(...)`
  - `_schedule_workbench_pair_relation_persist(...)`
  - `_persist_workbench_pair_relations_in_transaction(...)`
  - `WorkbenchRelationCommandRepositoryAdapter.save_workbench_pair_relations(...)`
  - `PostgresStateStore.save_workbench_pair_relations(...)`
  - `ApplicationStateStore.save_workbench_pair_relations(...)`
- Left app bootstrap loading through `load_workbench_pair_relations` unchanged.

## Preserved Semantics

- Broad app state saves still persist imports, categories, file imports, matching, workbench overrides, exception cases, no-OA batches, read models, candidate matches, dirty scopes, turnover, cost/tax read models and pending invoice commands.
- Relation writes still use the existing relation-specific persistence boundaries.
- Postgres mode still loads Workbench pair relations through the runtime domain loader instead of a full snapshot load.
- State-store domain snapshot contracts still round trip relation snapshots.

## Legacy Classification

- Removed from broad full-state path: Workbench relation snapshot facts.
- Retained compatibility:
  - State-store relation domain save/load methods.
  - Postgres fallback snapshot inside `PostgresStateStore.save_workbench_pair_relations(...)`.
  - Mongo/local detailed relation collections.
- Still open:
  - app health / route builder pair-service injection accounting.
  - final local module closure/defer accounting.
  - production evidence defer because local/staging `PGSQL_URL` is unavailable.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:persist-state-relation-snapshot-quarantine`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:app-health-route-builder-pair-service-injection-audit`

## Seven Test Category Decision

1. Business core unit tests: not applicable; relation business rules were not changed.
2. Service-layer tests: covered by state-store domain round-trip tests and Postgres mode bootstrap regression.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: covered by static guard preventing broad state saves from touching relation persistence; relation refresh enqueue code was not changed.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not added for this narrow internal persistence quarantine.
7. Existing feature regression tests: covered by app bootstrap/domain state-store regressions and persist boundary guards.

## Verification

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_broad_persist_state_does_not_serialize_pair_relations tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_pair_relation_persist_uses_explicit_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_transaction_pair_relation_persist_uses_relation_repository_owner -v
PYTHONPATH=backend/src python3 -m unittest tests.test_app_postgres_mode.AppPostgresModeTests.test_postgres_runtime_bootstrap_loads_pair_relations_without_full_snapshot -v
PYTHONPATH=backend/src python3 -m unittest tests.test_state_store_contract.StateStoreContractTests.test_state_store_domain_snapshot_contract_round_trips tests.test_postgres_state_store.PostgresStateStoreTests.test_postgres_store_snapshot_methods_round_trip -v
```

Pending final verification:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this implementation slice is closed. `workbench_relation` remains `implementation-gap-open`.
