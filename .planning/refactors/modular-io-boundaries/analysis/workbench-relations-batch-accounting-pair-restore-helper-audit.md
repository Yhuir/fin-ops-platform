# Workbench Relations Batch Accounting Pair Restore Helper Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:batch-accounting-pair-restore-helper-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Do not remove `_restore_batch_accounting_pair_relation_snapshot(...)`.

Select the next narrow implementation boundary:

`workbench-relations:batch-accounting-pair-restore-service-delegation`

The next slice should make the batch-accounting route-local restore callback delegate to `WorkbenchPairRelationRollbackRestoreService` in in-memory mode (`state_store=None`) instead of directly calling `WorkbenchPairRelationService.from_snapshot(...)` from `server.py`.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/routes_batch_accounting.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
- `tests/test_batch_accounting_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-restore-local-implementation-closure-audit.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

CodeGraph confirmed:

- `BatchAccountingApiRoutes` owns submit/withdraw DTO and route-side orchestration.
- `BatchAccountingApiRoutes.submit(...)` snapshots pair relation state before `BatchAccountingService.submit(...)` mutates relation state through the command service.
- If `_schedule_pair_relation_persist(...)` raises after submit, `BatchAccountingApiRoutes.submit(...)` calls the injected `restore_pair_relation_snapshot(...)` callback.
- `Application._batch_accounting_routes(...)` injects `pair_relation_snapshot=self._workbench_pair_relation_service.snapshot` and `restore_pair_relation_snapshot=self._restore_batch_accounting_pair_relation_snapshot`.
- `Application._restore_batch_accounting_pair_relation_snapshot(...)` currently rehydrates `WorkbenchPairRelationService.from_snapshot(snapshot)` directly and calls `_configure_workbench_exception_application_service()`.
- `WorkbenchPairRelationRollbackRestoreService.restore(...)` already centralizes the same restore semantics, and with `state_store=None` it only replaces the in-memory pair relation service and reconfigures exception application service without writing a rollback snapshot.

## Boundary Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| `BatchAccountingApiRoutes._pair_relation_snapshot` | route-local compat callback | It is a rollback checkpoint for submit persist failure, not a canonical read path. |
| `BatchAccountingApiRoutes._restore_pair_relation_snapshot` | route-local compat callback, implementation-gap-open | It must remain injectable for route owner isolation, but the app helper behind it should not own direct pair service rehydration. |
| `Application._restore_batch_accounting_pair_relation_snapshot(...)` | implementation-gap-open | It still directly constructs `WorkbenchPairRelationService.from_snapshot(...)`, duplicating rollback restore behavior already owned by `WorkbenchPairRelationRollbackRestoreService`. |
| `WorkbenchPairRelationRollbackRestoreService` | target owner | It already supports in-memory rollback when `state_store=None`, preserving batch-accounting's current no-state-store-save behavior. |

## Why Not Remove It

The helper is used by the batch-accounting submit failure path after relation mutation has already occurred but before pair relation persistence is accepted. Removing it would leave a half-mutated in-memory relation state if `_schedule_pair_relation_persist(...)` fails.

The route owner still needs a rollback callback. The implementation gap is not the callback itself; the gap is that `server.py` owns direct restore behavior instead of delegating to the explicit rollback restore service.

## Why Not Persist Rollback Snapshot Here

Existing batch-accounting behavior restores only the in-memory pair relation service and reconfigures the exception application service. It does not call `state_store.save_workbench_pair_relations(...)` during this rollback callback.

The next implementation slice must preserve that behavior unless a separate behavior-changing API/service test plan explicitly expands scope. Therefore the recommended delegation is an in-memory rollback service instance with `state_store=None`, not the normal WorkbenchWriteFacade rollback service that persists rollback state best-effort.

## Next Implementation Scope

Allowed next slice:

- Add an app-level factory such as `_batch_accounting_pair_relation_rollback_restore_service(...)` or equivalent dependency assembly.
- Keep `_restore_batch_accounting_pair_relation_snapshot(...)` as a compat-only wrapper because `BatchAccountingApiRoutes` still expects a route-local callback.
- Make the wrapper delegate to `WorkbenchPairRelationRollbackRestoreService.restore(snapshot, changed_case_ids=[])` with `state_store=None`.
- Add or extend static guard coverage proving the batch-accounting wrapper no longer contains `WorkbenchPairRelationService.from_snapshot(...)` or direct exception service reconfiguration.
- Add targeted API/service regression only if an existing test does not already cover submit persist failure rollback.

Forbidden next slice expansion:

- Do not change submit/withdraw business rules.
- Do not add rollback behavior to withdraw in this same slice.
- Do not change API payload shape, changed scope calculation, dirty scope semantics, or command service relation writes.
- Do not introduce Go/Fiber/Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice is analysis/accounting only. It closes as `analysis-closed`; `workbench_relation` remains `implementation-gap-open`.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not applicable. No business rule changed in this audit. |
| Service-layer tests | Not applicable for this audit. The next implementation slice should use the existing rollback restore service tests and add batch-accounting-specific coverage if needed. |
| API contract tests | Not applicable for this audit. The next implementation slice should preserve existing submit persist failure rollback response shape. |
| Read model/cache/background job tests | Not applicable. No read model or refresh behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable. No runtime behavior changed. |
| Existing feature regression tests | Applicable through impact review, docs verification and diff check. |

## Verification

Required before commit:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the batch-accounting pair restore helper audit. It does not implement the service delegation, close `workbench_relation`, validate production evidence, or unblock Go admission.
