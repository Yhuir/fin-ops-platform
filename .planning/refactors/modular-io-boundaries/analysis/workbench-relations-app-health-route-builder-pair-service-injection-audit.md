# Workbench Relations - App Health Route Builder Pair Service Injection Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:app-health-route-builder-pair-service-injection-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit App Health services and route/builder pair-service injections after broad full-state relation snapshot quarantine.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-persist-state-relation-snapshot-quarantine.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-server-precondition-local-implementation-closure-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/app_health_alert_service.py`
- `backend/src/fin_ops_platform/services/app_status_overview_service.py`
- `backend/src/fin_ops_platform/app/routes_batch_accounting.py`
- `backend/src/fin_ops_platform/services/settings_data_reset_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Findings

`AppHealthAlertService` and `AppStatusOverviewService` do not accept or call `WorkbenchPairRelationService`. They consume app health/read-model/worker/outbox snapshots and registry definitions only. There is no App Health pair-service pollution to remove.

Remaining route/builder pair-service related surfaces:

| Surface | Classification | Evidence | Decision |
| --- | --- | --- | --- |
| `AppHealthAlertService` / `AppStatusOverviewService` | no relation dependency | Text search and source review show no `pair_relation_service` or `_workbench_pair_relation_service` dependency. | Closed for this audit. |
| `SettingsDataResetService(workbench_pair_relation_service=...)` | later accounting candidate | Reset OA flows intentionally inspect and persist relation snapshots to preserve non-OA relations and remove OA/attachment relations. Existing tests cover this behavior. | Not the next smallest boundary because turnover builder still passes broad pair service into a lower-level snapshot/restore connection with private-field restore. |
| `NoOaPairRelationSnapshotPort(self._workbench_pair_relation_service)` | accepted explicit port assembly | Earlier no-OA slices extracted the broad service behind a dedicated snapshot port; `NoOaBankBatchApplicationService` no longer stores broad pair service. | No code slice needed. |
| `BatchAccountingApiRoutes(pair_relation_snapshot=..., restore_pair_relation_snapshot=...)` | compat-only route rollback callbacks | Earlier rollback accounting classified this as route-local rollback compatibility; restore delegates to `WorkbenchPairRelationRollbackRestoreService` with `state_store=None`. | No code slice needed before turnover local snapshot port. |
| `TurnoverLedgerConfirmPrimaryWriteFacadeBuilder(pair_relation_service=...)` and withdraw builder equivalent | next implementation boundary | Primary turnover builders still receive broad pair service only to build local transaction support/rollback connection. `TurnoverLedgerLocalClosureConnection` directly snapshots, saves and restores pair relation state, including private `_pair_relations` / `_pair_relation_history` assignment. | Extract explicit turnover local pair snapshot/restore port next. |
| Existing relation read/write route builders | accepted explicit boundaries | Pending invoice, OA pending payment, output invoice collection, no-OA and cost routes use `relation_facade`, `relation_command_service`, or explicit relation ports. | No code slice needed. |

## Decision

Do not mark `workbench_relation` closed.

Do not run Go admission.

Queue a narrow implementation boundary:

`workbench-relations:turnover-local-pair-snapshot-port-extraction`

Expected implementation direction:

- Add an explicit turnover local pair snapshot/restore port or reuse an existing dedicated snapshot port if it fits exactly.
- Remove broad `pair_relation_service` from turnover primary builder constructors and `TurnoverLedgerLocalClosureConnection`.
- Preserve local transaction rollback semantics for confirm/withdraw.
- Preserve command-service writes, relation facade reads and route response shape.
- Add or update static guard coverage proving turnover primary builders/local connection no longer accept broad pair service.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:app-health-route-builder-pair-service-injection-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:turnover-local-pair-snapshot-port-extraction`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no behavior changed.
2. Service-layer tests: not added; this is analysis-only.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: not applicable; no runtime read model behavior changed.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not applicable for this audit-only slice.
7. Existing feature regression tests: not run because this slice only records dependency accounting.

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this audit slice is closed. `workbench_relation` remains `implementation-gap-open`.
