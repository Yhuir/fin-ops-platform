# Workbench Relations - Transaction Persist Closure Accounting Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:transaction-persist-closure-accounting-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit transaction and non-transaction Workbench relation persist surfaces after the case-id allocator extraction, without changing relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-case-id-allocation-service-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-server-precondition-local-implementation-closure-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_persist_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench_relation.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/workbench.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_workbench_pair_relation_persist_service.py`
- `tests/test_workbench_pair_relation_rollback_restore_service.py`
- CodeGraph context for `_persist_workbench_pair_relations`, `_persist_workbench_pair_relations_in_transaction`, `WorkbenchPairRelationPersistService`, `PostgresWorkbenchRelationRepository.save_workbench_pair_relations`, and `snapshot_case_ids`.

## Persist Surface Accounting

| Surface | Classification | Evidence | Closure Decision |
| --- | --- | --- | --- |
| `_persist_workbench_pair_relations(...)` | implemented compat delegate | Delegates to `WorkbenchPairRelationPersistService.persist(...)` and syncs compatibility state only. Static guard forbids inline `save_workbench_pair_relations`, pending-case mutation, thread creation and timing emission in the wrapper. | No code slice needed for this surface. Keep wrapper until app wiring stops needing legacy callback shape. |
| `_schedule_workbench_pair_relation_persist(...)` | implemented compat delegate | Delegates to `WorkbenchPairRelationPersistService.schedule(...)`; coalescing and timing behavior live in the service. | No code slice needed for this surface. |
| `_persist_workbench_pair_relations_in_background(...)` | implemented compat delegate | Rehydrates service compatibility state, delegates to `persist_in_background(...)`, then syncs state back. Guard prevents behavior from returning to `server.py`. | No code slice needed for this surface. |
| `WorkbenchPairRelationPersistService` | implemented service boundary | Owns non-transactional cache clear, snapshot selection, state-store save, async coalescing, background stale-version skip and action timing. Unit tests cover changed-case snapshot save, async coalescing and sync timing. | Local implementation closed for non-transactional persist behavior. Not module closure proof. |
| `_persist_workbench_pair_relations_in_transaction(...)` | implemented transaction assembly | Requires a transaction, clears search cache, snapshots all or changed case ids and calls `PostgresWorkbenchRelationRepository(transaction).save_workbench_pair_relations(...)`. Static guard forbids broad `PostgresWorkbenchRepository(transaction).save_workbench_pair_relations(...)`. | Accept as app-level transaction assembly for now; no behavior-preserving extraction is required before rollback/whole-state accounting. |
| `PostgresWorkbenchRelationRepository.save_workbench_pair_relations(...)` | implemented repository owner | Owns relation SQL upsert/history replacement plus in-transaction high-priority dirty/outbox enqueue for `workbench_relation`, `workbench`, pending invoice and downstream read models. Broad `PostgresWorkbenchRepository.save_workbench_pair_relations(...)` is now a compatibility delegate. | Relation SQL owner split is implemented; broad repository compatibility method remains a later deletion/quarantine candidate, not a transaction persist blocker. |
| `WorkbenchPairRelationService.snapshot_case_ids(...)` | implemented domain snapshot helper | Returns deep-copied changed relation cases plus history. Tests prove only requested relation cases are included. | Required until canonical relation command repository stops using in-memory snapshot semantics. Not a transaction persist blocker. |

## Remaining Gaps

This audit does not close `workbench_relation`.

Persist-specific surfaces are locally accounted for, but broader closure still needs separate slices:

- rollback restore closure accounting: `_restore_workbench_pair_relation_snapshot(...)`, `WorkbenchPairRelationRollbackRestoreService`, exception rollback restore, batch-accounting restore delegation and failure-recovery semantics need one final accounting pass before any module defer/closure claim.
- whole-state persistence snapshot accounting: `_persist_state(...)`, app bootstrap `WorkbenchPairRelationService.from_snapshot(...)`, Mongo/local state-store compatibility and production PostgreSQL canonical write ownership still need classification.
- app health / route builder pair-service injection accounting remains open from the earlier local implementation closure audit.
- production evidence remains deferred because there is no local/staging `PGSQL_URL`; root SSH is available only for read-only production checks and must not perform production writes.

## Decision

Do not implement Go/Fiber/Go Worker next.

Do not mark `workbench_relation` closed or production-evidence-deferred.

Mark this transaction persist accounting slice as `analysis-closed`, keep module closure as `implementation-gap-open`, and queue:

`workbench-relations:rollback-closure-accounting-audit`

The next audit should verify rollback restore surfaces are either already owned by explicit services or still need one more implementation slice. It should not change business behavior unless the audit finds a narrow, testable rollback ownership gap.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:transaction-persist-closure-accounting-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:rollback-closure-accounting-audit`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business behavior changed.
2. Service-layer tests: existing persist service and rollback restore service tests were reviewed; no new code changed.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: not added; audit reviewed existing persistence and dirty/outbox ownership but made no runtime change.
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
