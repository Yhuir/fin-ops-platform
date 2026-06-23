# Workbench Relation Post-Restore Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:post-restore-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

Do not mark `workbench_relation` locally closed or production-evidence-deferred yet.

Select the next narrow audit:

`workbench-relations:batch-accounting-pair-restore-helper-audit`

## Evidence Reviewed

Completed local support slices now include:

- read model repository port extraction;
- derived lifecycle executor extraction;
- transaction persist repository owner split;
- command repository snapshot adapter extraction;
- non-transactional pair relation persist service extraction;
- pair relation rollback restore service extraction;
- exception rollback restore service extraction.

Remaining app-owned relation surfaces found by text search:

- WorkbenchWriteFacade callback wiring in `_workbench_write_facade(...)`: now mostly dependency assembly with explicit services/wrappers.
- `_restore_batch_accounting_pair_relation_snapshot(...)`: still route-local app helper that directly rebuilds `WorkbenchPairRelationService.from_snapshot(...)` and reconfigures exception application service.
- `BatchAccountingApiRoutes` wiring still receives `pair_relation_snapshot=self._workbench_pair_relation_service.snapshot` and `restore_pair_relation_snapshot=self._restore_batch_accounting_pair_relation_snapshot`.
- Turnover ledger primary/legacy fallback facades still receive `pair_relation_service`, relation command factory and persist callbacks for closure/withdraw paths.
- No-OA and pending-invoice application/query services still receive `pair_relation_service` alongside relation command service/facade; these need separate classification before any full module closure claim.
- Historical ETC repair still receives relation command service plus pair persist callback.

## Closure Assessment

| Requirement | Local status |
| --- | --- |
| IO contract | partially satisfied through read facade, command service and extracted persist/restore services |
| Public/internal boundary | still open because route-local and legacy fallback pair relation callbacks remain |
| Canonical fact owner | partially satisfied; command service/repository adapter owns canonical writes for many paths, but some legacy/fallback paths still require classification |
| Shared fact source | partially satisfied; `workbench_relation` read model remains shared downstream source |
| Read model/freshness/force refresh/operation barrier | locally covered by existing read facade/lifecycle/UoW tests, production evidence deferred |
| Legacy removal/quarantine | incomplete |
| Permission/audit/test contracts | partially covered by existing Workbench/route tests; not full module closed |
| Environment evidence | production PostgreSQL/worker/App Status/high-row/browser evidence still unavailable in this local run |

## Next Boundary Rationale

`_restore_batch_accounting_pair_relation_snapshot(...)` is the smallest remaining app-owned relation restore helper:

- it is isolated to `BatchAccountingApiRoutes` wiring;
- it directly rehydrates pair relation service from snapshot;
- it is adjacent to already-completed pair rollback restore extraction;
- it can likely be audited and either delegated to `WorkbenchPairRelationRollbackRestoreService` or classified as route-local compat-only without touching turnover/no-OA/pending-invoice flows.

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
| Business core unit tests | Not applicable. No behavior changed in this audit. |
| Service-layer tests | Not applicable for this audit. |
| API contract tests | Not applicable. No HTTP behavior changed. |
| Read model/cache/background job tests | Not applicable. No runtime behavior changed. |
| Frontend component and interaction tests | Not applicable. |
| End-to-end business-flow integration tests | Not applicable. |
| Existing feature regression tests | Applicable through docs/diff verification and impact review. |

## Verification

Pending before commit:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only the post-restore local implementation closure audit. It does not close `workbench_relation`, validate production evidence, or unblock Go admission.
