# Workbench Relations No-OA Pair Service Boundary Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:no-oa-pair-service-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit no-OA relation dependencies and classify remaining `pair_relation_service` usage before choosing the next narrow boundary.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-pending-invoice-unused-pair-service-removal.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `docs/modules/no-oa-bank-batches/README.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`
- `docs/modules/no-oa-bank-batches/tests.md`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/no_oa_legacy_relation_migration_service.py`
- `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_no_oa_bank_batch_service.py`
- `tests/test_no_oa_bank_batch_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `NoOaBankBatchService`, `NoOaBankBatchApplicationService`, `pair_relation_service`, `relation_facade`, and `relation_command_service`.

## Findings

No-OA is not in the same state as pending invoice. The remaining pair service dependency is not purely unused.

`NoOaBankBatchApplicationService` still requires `pair_relation_service` for snapshot and rollback behavior:

- Captures `previous_relation_snapshot = self._pair_relation_service.snapshot()` before submit/submit-selection/internal-transfer/withdraw mutations.
- Persists relation snapshots through `save_no_oa_bank_batch_mutation(...)` or fallback `save_workbench_pair_relations(...)`.
- Computes `pair_relation_snapshot_version` for source-version accounting.
- Exposes `pair_relation_snapshot_by_case_id(...)` for targeted read/diagnostic flows.
- Restores `_pair_relations` and `_pair_relation_history` directly during rollback.

`NoOaBankBatchApplicationService` normal relation writes are already command-service gated:

- `_confirm_relation_for_batch(...)` calls `relation_command_service.confirm_relation(...)`.
- `_cancel_relation_for_batch(...)` calls `relation_command_service.cancel_relation(...)`.
- Missing command service fails fast with `no_oa_bank_batch_relation_command_unavailable`.

`NoOaBankBatchApplicationService` relation reads for active rows are already facade-backed:

- `_workbench_relation_rows_by_id(...)` uses `relation_facade.get_by_row_ids(...)`.
- `_workbench_relation_active_relations_for_bank_rows(...)` uses `relation_facade.list_by_month(...)`.

`NoOaBankBatchService` still holds `_pair_relation_service` for legacy/read/repair classification:

- `_repair_submitted_no_oa_relation_consistency(...)` checks active relation by case id and active relations for row ids before command-service-backed repair.
- `_has_active_no_oa_relation(...)` uses `get_active_relation_by_case_id(...)` to project relation-backed stale/superseded batches as submitted.
- `_build_batches_for_month_scope(...)` passes the same pair service into a scoped service for month refresh.
- Legacy repair/consolidation writes are already command-service-backed through `_confirm_no_oa_relation(...)` and `_cancel_no_oa_relation(...)`.

`NoOaLegacyRelationMigrationService` no longer keeps direct pair relation read/write dependency according to the existing guard. It uses command-service helpers and fails fast without command service.

`no_oa_bank_batch.read_model.refresh` is already guarded so worker refresh cannot run relation repair or pair relation persistence side effects.

## Classification

| Surface | Current classification | Target classification | Evidence |
| --- | --- | --- | --- |
| `NoOaBankBatchApplicationService.relation_command_service` | canonical write dependency | keep | Normal submit/withdraw/internal transfer writes call command service. |
| `NoOaBankBatchApplicationService.relation_facade` | canonical read dependency | keep | Active row/detail reads use read facade. |
| `NoOaBankBatchApplicationService.pair_relation_service` snapshot/persist/rollback usage | legacy snapshot port embedded in application service | extract to explicit snapshot/rollback/persist port | Required today for rollback and state-store persistence; should not stay as broad pair service injection. |
| `NoOaBankBatchApplicationService.pair_relation_snapshot_by_case_id(...)` | compat read helper | classify in later slice | Reads snapshot directly for targeted diagnostics; not a write path. |
| `NoOaBankBatchService._pair_relation_service` repair/read usage | compat-only read/repair input | migrate later to read facade or repair read port | Still needed for submitted relation repair and relation-backed stale projection. |
| `NoOaLegacyRelationMigrationService` relation dependency | command-service-only | keep | Existing guard forbids pair service dependency and direct pair writes. |
| `no_oa_bank_batch.read_model.refresh` relation side effects | forbidden | keep guard | Existing guard requires `apply_relation_repairs=False` and forbids relation writes. |

## Decision

The next boundary should be:

`workbench-relations:no-oa-application-pair-snapshot-port-extraction`

Scope:

- Extract the `NoOaBankBatchApplicationService` pair snapshot/version/persist/rollback interactions into an explicit collaborator or port.
- Keep normal relation writes on `WorkbenchRelationCommandService`.
- Keep relation reads on `WorkbenchRelationReadFacade`.
- Preserve existing rollback semantics when persistence fails.
- Preserve state store payload shape for `save_no_oa_bank_batch_mutation(...)` and fallback `save_workbench_pair_relations(...)`.
- Add/strengthen tests proving no-OA application relation writes still do not call direct pair mutation and that app service no longer reaches into `_pair_relations` / `_pair_relation_history` directly.

Not in scope for the next slice:

- Do not migrate `NoOaBankBatchService._repair_submitted_no_oa_relation_consistency(...)`.
- Do not migrate `_has_active_no_oa_relation(...)`.
- Do not change no-OA submit/withdraw/internal transfer business rules, API payloads, dirty scope semantics, read model refresh semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/no-oa-bank-batches/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This audit classifies no-OA dependencies and selects the next extraction boundary. `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No business behavior changed. |
| Service-layer tests | Not changed in this audit slice. Next implementation slice should run no-OA application service/API rollback tests and boundary guards. |
| API contract tests | Not applicable. No HTTP/API shape changed. |
| Read model/cache/background job tests | Not applicable. No refresh, dirty scope, cache or worker behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice. |
| Existing feature regression tests | Existing no-OA tests and guards were inspected; next implementation slice must run targeted no-OA service/API/guard tests. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only no-OA pair service dependency classification. It does not remove code, close `workbench_relation`, validate production evidence, or unblock Go admission.
