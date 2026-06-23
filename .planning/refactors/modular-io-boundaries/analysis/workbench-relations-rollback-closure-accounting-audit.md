# Workbench Relations - Rollback Closure Accounting Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:rollback-closure-accounting-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit Workbench relation rollback restore surfaces after transaction persist accounting, without changing relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-transaction-persist-closure-accounting-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-pair-relation-rollback-restore-service-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-exception-rollback-restore-service-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
- `backend/src/fin_ops_platform/services/workbench_exception_rollback_restore_service.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_workbench_pair_relation_rollback_restore_service.py`
- `tests/test_workbench_exception_rollback_restore_service.py`
- CodeGraph context for rollback restore surfaces.

## Rollback Surface Accounting

| Surface | Classification | Evidence | Closure Decision |
| --- | --- | --- | --- |
| `_restore_workbench_pair_relation_snapshot(...)` | implemented compat delegate | Delegates to `WorkbenchPairRelationRollbackRestoreService.restore(...)`; static guard forbids `WorkbenchPairRelationService.from_snapshot`, direct `save_workbench_pair_relations(...)` and direct exception application reconfigure inside the wrapper. | No code slice needed. Keep wrapper for `WorkbenchWriteFacade` callback compatibility. |
| `WorkbenchPairRelationRollbackRestoreService` | implemented service boundary | Owns snapshot rehydrate, pair relation service replacement, exception application service reconfigure and best-effort state-store save. Service tests cover successful restore and state-store failure after in-memory replacement. | Local rollback restore behavior is accounted for. |
| `_replace_workbench_pair_relation_service(...)` | implemented compatibility state reset | Centralizes pair relation service replacement and clears cached `WorkbenchPairRelationPersistService` instance so future persists do not target stale service state. Static guard covers this. | No code slice needed. |
| `_restore_workbench_exception_write_snapshots(...)` | implemented compat delegate | Delegates to `WorkbenchExceptionRollbackRestoreService.restore_write_snapshots(...)`; static guard forbids direct exception/pair/candidate/override snapshot rehydrate in the wrapper. | No code slice needed. |
| `_restore_workbench_exception_pair_snapshots(...)` | implemented compat delegate | Delegates to `restore_pair_snapshots(...)`; used by Workbench exception pair rollback paths. | No code slice needed. |
| `_restore_workbench_exception_override_snapshots(...)` | implemented compat delegate | Delegates to `restore_override_snapshots(...)`; best-effort exception snapshot save lives in the service. | No code slice needed. |
| `WorkbenchExceptionRollbackRestoreService` | implemented service boundary | Owns exception, pair relation, candidate match and override snapshot restoration plus exception application service reconfigure where needed. Service tests cover write, pair and override restore methods. | Local exception rollback restore behavior is accounted for. |
| `_restore_batch_accounting_pair_relation_snapshot(...)` | implemented route-local compat delegate | Delegates to a `WorkbenchPairRelationRollbackRestoreService` instance with `state_store=None`, preserving in-memory rollback-only behavior and `changed_case_ids=[]`. Static guard covers no-persist behavior. | No code slice needed. |

## Remaining Gaps

Rollback-specific surfaces are locally accounted for, but `workbench_relation` is still not module-closed.

Open work remains:

- whole-state persistence snapshot / bootstrap compatibility accounting: `_persist_state(...)`, `PostgresStateStore.save_workbench_pair_relations(...)`, local/Mongo state-store compatibility and app startup `WorkbenchPairRelationService.from_snapshot(...)`.
- app health / route builder pair-service injection accounting from earlier local implementation closure audit.
- production evidence remains deferred because no local/staging `PGSQL_URL` exists; SSH root may only be used for read-only checks and must not perform production writes.
- broader read model implementation and Go hot-path admission remain blocked until module IO closure and freshness proof exist.

## Decision

Do not implement Go/Fiber/Go Worker next.

Do not mark `workbench_relation` closed or production-evidence-deferred.

Mark this rollback accounting slice as `analysis-closed`, keep module closure as `implementation-gap-open`, and queue:

`workbench-relations:whole-state-persistence-closure-accounting-audit`

The next audit should classify full-state persistence, bootstrap and compatibility snapshot paths before any final local closure/defer decision.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:rollback-closure-accounting-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:whole-state-persistence-closure-accounting-audit`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business behavior changed.
2. Service-layer tests: existing pair and exception rollback restore service tests were reviewed; no new code changed.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: not added; audit reviewed rollback cache consistency but made no runtime change.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not applicable for this analysis-only slice.
7. Existing feature regression tests: not run because this slice only records closure accounting.

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this audit slice is closed. `workbench_relation` remains `implementation-gap-open`.
