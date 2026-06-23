# Workbench Relation Restore Pair Relation Snapshot Helper Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:restore-pair-relation-snapshot-helper-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Select a narrow rollback restore extraction next:

`workbench-relations:pair-relation-rollback-restore-service-extraction`

`_restore_workbench_pair_relation_snapshot(...)` is not removable. It is used by `WorkbenchWriteFacade` failure paths to restore the previous relation snapshot after a relation command has mutated in-memory state but subsequent persistence, reconciliation-decision consumption or read-model scheduling fails.

## Evidence

Current app helper:

- `Application._restore_workbench_pair_relation_snapshot(snapshot, *, changed_case_ids)`

Behavior:

- Replaces `Application._workbench_pair_relation_service` from the previous snapshot.
- Reconfigures `WorkbenchExceptionApplicationService` so exception application sees the restored pair relation service.
- Best-effort saves the previous snapshot through `state_store.save_workbench_pair_relations(...)` when a state store exists.
- Swallows persistence errors during rollback restore, matching existing best-effort rollback behavior.

Callers:

- `WorkbenchWriteFacade.confirm_link(...)` non-UoW fallback after schedule/decision-consume failure.
- `WorkbenchWriteFacade.confirm_link(...)` UoW broad failure catch.
- `WorkbenchWriteFacade.cancel_link(...)` non-UoW fallback after schedule failure.
- `WorkbenchWriteFacade.cancel_link(...)` UoW broad failure catch.
- `WorkbenchWriteFacade.withdraw_link(...)` non-UoW fallback after schedule/read-model invalidation failure.
- `WorkbenchWriteFacade.withdraw_link(...)` UoW broad failure catch.

Related but separate restore helpers:

- `_restore_workbench_exception_pair_snapshots(...)` restores exception cases and pair relations together for exception/personal-advance paths.
- `_restore_workbench_exception_write_snapshots(...)` restores exception, override and pair snapshots.
- `_restore_batch_accounting_pair_relation_snapshot(...)` is a batch-accounting local snapshot restore that does not persist to state store.

## Boundary Selection

The next implementation should extract only this rollback restore behavior into an explicit service, suggested:

- file: `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
- class: `WorkbenchPairRelationRollbackRestoreService`

Suggested dependencies:

- `state_store`;
- `replace_pair_relation_service` callback or holder;
- `configure_exception_application_service` callback;
- optional logger only if existing error swallowing needs observable logging without changing behavior.

Do not merge this into `WorkbenchPairRelationPersistService`. Persist/schedule is normal forward progress; rollback restore is failure recovery and should remain separately testable.

## Legacy Path Classification

- `_restore_workbench_pair_relation_snapshot(...)`: implementation-pending; should become a compat-only delegate after extraction.
- `_restore_workbench_exception_pair_snapshots(...)`: separate rollback helper, not in the next slice unless analysis proves the new service can be reused without broadening scope.
- `_restore_workbench_exception_write_snapshots(...)`: separate rollback helper, not in the next slice.
- `_restore_batch_accounting_pair_relation_snapshot(...)`: separate route-local rollback helper, not in the next slice.
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
| Business core unit tests | Not applicable. No relation business rule changed in this audit. |
| Service-layer tests | Not applicable for this audit. The next implementation should add rollback restore service tests. |
| API contract tests | Not applicable. No HTTP behavior changed. |
| Read model/cache/background job tests | Not applicable. No runtime behavior changed in this audit. |
| Frontend component and interaction tests | Not applicable. |
| End-to-end business-flow integration tests | Not applicable. |
| Existing feature regression tests | Applicable through CodeGraph/text impact review and existing Workbench write characterization/UoW rollback tests identified as follow-up verification. |

## Verification

Pending before commit:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the rollback restore helper audit. It does not extract code, close `workbench_relation`, validate production evidence or unblock Go admission.
