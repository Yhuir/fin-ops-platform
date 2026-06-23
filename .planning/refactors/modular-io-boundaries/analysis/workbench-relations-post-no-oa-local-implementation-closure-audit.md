# Workbench Relations Post No-OA Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:post-no-oa-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Re-audit local `workbench_relation` implementation gaps after pending invoice, turnover and no-OA relation dependency extractions, and select the next narrow boundary without jumping to Go admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-no-oa-domain-repair-read-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
- `backend/src/fin_ops_platform/services/etc_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_workbench_write_characterization.py`
- CodeGraph context for relation command/read facade boundaries.
- Text search for `_workbench_pair_relation_service`, `pair_relation_service=`, `WorkbenchPairRelationService`, `replace_pair_relation_service`, `WorkbenchWriteFacade`, `EtcBusinessBatchApplicationService`, and `EtcService`.

## Findings

`workbench_relation` remains `implementation-gap-open`.

Already extracted or guarded:

- Read model repository port and derived lifecycle executor are implemented.
- Transaction-bound pair relation persistence uses `PostgresWorkbenchRelationRepository`.
- Command repository snapshot/apply is behind `WorkbenchRelationCommandRepositoryAdapter`.
- Non-transactional pair relation persist/schedule/background is behind `WorkbenchPairRelationPersistService`.
- Pair relation rollback restore is behind `WorkbenchPairRelationRollbackRestoreService`.
- Exception rollback restore is behind `WorkbenchExceptionRollbackRestoreService`.
- Batch-accounting pair restore delegates to rollback restore service.
- Turnover unused persist callback is removed; turnover writes are command-service gated.
- Pending invoice no longer accepts pair service.
- No-OA application snapshot/persist/rollback is behind `NoOaPairRelationSnapshotPort`.
- No-OA domain repair/read active relation reads are behind `NoOaRelationRepairReadPort`.

ETC is not the highest-risk next boundary:

- `EtcBusinessBatchApplicationService` is constructed from ETC services, OA client factory, invoice-link callback and refresh callback.
- The visible ETC business batch route/application construction does not inject `WorkbenchPairRelationService`.
- Existing guards already cover ETC summary delete command-boundary behavior and historical ETC migration command fallback constraints.
- ETC may still need a later focused audit, but current evidence shows it is not the biggest remaining direct broad pair service holder.

The largest remaining local relation boundary is `WorkbenchWriteFacade`:

- `Application._workbench_write_facade(...)` still injects `pair_relation_service=self._workbench_pair_relation_service`.
- `WorkbenchWriteFacade` stores `_pair_relation_service`.
- It still directly reads pair relation state for preview/confirm/cancel/withdraw/special-metadata flows.
- It still snapshots pair relations for rollback and operation payloads.
- It already uses command service for core confirm/cancel paths where available, and existing guards prevent direct confirm/cancel pair write fallback in the most important methods.
- It is too broad for immediate extraction without first classifying read, snapshot, rollback, special metadata and command fallback surfaces.

## Decision

The next boundary should be:

`workbench-relations:workbench-write-facade-pair-service-boundary-audit`

Scope:

- Audit every `WorkbenchWriteFacade._pair_relation_service` call site.
- Classify each call as:
  - command write path that should use `WorkbenchRelationCommandService`.
  - read/preflight path that should move behind a relation read port/facade.
  - snapshot/rollback path that should move behind snapshot/rollback ports.
  - special metadata mutation path that needs command-service support or a separate port.
  - compat-only path with owner, caller list, deletion condition and guard.
- Determine the next narrow implementation boundary, likely not the full facade in one slice.
- Preserve existing Workbench confirm/cancel/withdraw/idempotency/UoW behavior.

Not in scope for the next slice:

- Do not implement Go/Fiber/Go Worker.
- Do not migrate all of `WorkbenchWriteFacade` in one step.
- Do not change relation write semantics, API payloads, dirty scope semantics, read model refresh semantics or Workbench active generation semantics.
- Do not declare `workbench_relation` closed.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/workbench-relations/state-machine.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`

No global or module state definition changes are required. This slice reclassifies the next local gap only. `workbench_relation` remains `implementation-gap-open`, and Go admission remains blocked.

## Seven Test Categories

| Category | Applies? | Evidence |
| --- | --- | --- |
| Business core unit tests | Not changed in this audit slice. |
| Service-layer tests | Not changed in this audit slice. Next implementation should run Workbench write characterization tests. |
| API contract tests | Not applicable. No HTTP/API shape changed. |
| Read model/cache/background job tests | Not applicable. No refresh, dirty scope, cache or worker behavior changed. |
| Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| End-to-end business-flow integration tests | Not applicable for this analysis-only slice. |
| Existing feature regression tests | Existing Workbench write guards and characterization tests were inspected as next-slice coverage candidates. |

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only post-no-OA local gap classification. It does not close `workbench_relation`, migrate `WorkbenchWriteFacade`, validate production PostgreSQL/worker evidence, or unblock Go admission.
