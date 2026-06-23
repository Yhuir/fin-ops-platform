# Workbench Relations - Local Implementation Closure And Production Evidence Defer

**Date:** 2026-06-24
**Boundary:** `workbench-relations:local-implementation-closure-and-production-evidence-defer`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Decide whether the current local `workbench_relation` implementation support can be marked `production-evidence-deferred`, or whether more local implementation/accounting slices are required before any Go admission.

## Evidence Reviewed

- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- ETC repair/link/migration tests referenced from module notes.

## Findings

Local implementation closure cannot be marked as production-evidence-deferred yet.

The remaining local gap is not merely missing production DB/worker evidence. The current docs and code still have ETC repair/link/migration services receiving `persist_pair_relations` callback wiring:

- `HistoricalEtcRepairService`
- `HistoricalEtcBusinessBatchMigrationService`
- `ExistingEtcBatchLinkService`
- `Application` wiring and migration/link tools that inject `app._persist_workbench_pair_relations(...)`

These services use `WorkbenchRelationCommandService` for the relation write itself, and existing docs/tests already state that command service must be available before local ETC writes. However, the callback remains part of relation metadata/update side-effect accounting. Before local closure/defer, it needs a narrow audit to classify whether it is:

- legitimate explicit post-command persist boundary;
- removable because command repository persistence is now authoritative;
- compat-only tool/test callback;
- or an implementation gap requiring a port or deletion.

## Decision

Do not move `workbench_relation` to `production-evidence-deferred`.

Insert a new boundary before Go admission:

`workbench-relations:etc-repair-link-migration-persist-callback-closure-audit`

Go hot-path candidates remain `blocked-by-prerequisite`.

## Legacy Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| `WorkbenchWriteFacade` pair ports | locally implemented explicit boundary | Broad constructor injection removed; remaining ports are explicit read/snapshot and special metadata mutation boundaries. |
| turnover local pair snapshot | locally implemented explicit boundary | `TurnoverLedgerLocalPairSnapshotPort` owns local snapshot/restore. |
| settings data reset pair snapshot | locally implemented explicit boundary | `SettingsDataResetPairSnapshotPort` owns reset-scoped snapshot/save. |
| relation command repository adapter | locally implemented explicit boundary | Owns command repository snapshot merge/apply. |
| transaction relation persist | locally implemented repository boundary | Uses `PostgresWorkbenchRelationRepository`. |
| rollback restore | locally implemented compat boundary | Dedicated rollback restore services own snapshot restore. |
| full app `_persist_state(...)` | locally quarantined | Relation snapshot removed from broad state persist. |
| ETC repair/link/migration `persist_pair_relations` callback | implementation-gap-open | Needs narrow closure audit before local closure/defer. |

## Production Evidence

Unavailable locally:

- real PostgreSQL relation table/history replay evidence;
- worker dirty/outbox/readiness evidence;
- App Status production relation readiness evidence;
- high-row performance evidence;
- browser smoke over production-like data.

These can become `production-evidence-deferred` only after local implementation gaps are closed. They do not justify skipping the ETC callback accounting gap.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:local-implementation-closure-and-production-evidence-defer`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:etc-repair-link-migration-persist-callback-closure-audit`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business behavior changed.
2. Service-layer tests: not applicable for this audit-only slice; next slice should inspect ETC service tests.
3. API contract tests: not applicable; no API changed.
4. Read model/cache/background job tests: not applicable; no runtime behavior changed.
5. Frontend component and interaction tests: not applicable.
6. End-to-end business-flow integration tests: not applicable for this audit-only slice.
7. Existing feature regression tests: existing ETC repair/link/migration tests identified for the next slice.

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this closure/defer audit slice is closed. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.
