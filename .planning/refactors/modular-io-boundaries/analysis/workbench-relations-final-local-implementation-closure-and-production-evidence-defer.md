# Workbench Relations - Final Local Implementation Closure And Production Evidence Defer

**Date:** 2026-06-24
**Boundary:** `workbench-relations:final-local-implementation-closure-and-production-evidence-defer`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Goal

Retry local `workbench_relation` closure/defer accounting after ETC repair/link/migration callback classification, without hiding local implementation gaps as production evidence gaps and without unlocking Go hot-path admission prematurely.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-local-implementation-closure-and-production-evidence-defer.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-etc-repair-link-migration-persist-callback-closure-audit.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_persist_service.py`
- `backend/src/fin_ops_platform/services/workbench_relation_command_repository_adapter.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `backend/src/fin_ops_platform/tools/repair_workbench_pair_relation_integrity.py`
- `backend/src/fin_ops_platform/tools/repair_no_oa_bank_batch_lifecycle.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Structural And Literal Checks

- CodeGraph status: index is healthy for the workspace.
- CodeGraph context surfaced the expected explicit boundary classes:
  - `WorkbenchPairRelationPersistService`
  - `NoOaRelationRepairReadPort`
  - `NoOaPairRelationSnapshotPort`
- Literal scan reviewed remaining `pair_relation_service`, `_pair_relation_service`, `workbench_pair_relations`, `persist_pair_relations`, `load_workbench_pair_relations` and `save_workbench_pair_relations` references in app, services, tools and boundary guard tests.

## Findings

No new local implementation gap was identified after ETC callback classification.

Remaining direct relation references are classified as explicit boundaries, repository ownership, runtime snapshot construction, tools, or tests:

| Surface | Classification | Evidence |
| --- | --- | --- |
| `WorkbenchWriteRelationReadSnapshotPort` | explicit read/snapshot port | `WorkbenchWriteFacade` no longer accepts broad `pair_relation_service`; static guard requires read/snapshot port injection. |
| `WorkbenchWriteRelationSpecialMetadataMutationPort` | explicit special metadata mutation port | Static guard rejects direct special metadata pair-service calls inside `WorkbenchWriteFacade`. |
| `WorkbenchPairRelationPersistService` | explicit non-transactional persist boundary | App persist/schedule/background wrappers delegate to this service; guard rejects behavior returning to `server.py` wrappers. |
| `WorkbenchRelationCommandRepositoryAdapter` | explicit command repository adapter | Adapter owns snapshot load/save/apply behavior for command service; guard rejects old app-level callback repository helpers. |
| transaction persist | repository boundary | `_persist_workbench_pair_relations_in_transaction(...)` uses `PostgresWorkbenchRelationRepository`, not broad `PostgresWorkbenchRepository`. |
| rollback restore services | explicit rollback compatibility boundary | Pair relation and exception rollback restore behavior is centralized in dedicated services; app wrappers are delegates. |
| broad `_persist_state(...)` | quarantined | Static guard proves Workbench relation snapshot facts are no longer serialized by broad app state persistence. |
| `NoOaPairRelationSnapshotPort` | explicit no-OA application snapshot/restore port | No-OA application service receives the port, not broad pair service. |
| `NoOaRelationRepairReadPort` | explicit no-OA domain repair/read port | `NoOaBankBatchService` stores `_relation_read_port`; guard rejects direct `_pair_relation_service` reads inside the service body and rejects direct write fallback. |
| `TurnoverLedgerLocalPairSnapshotPort` | explicit turnover local rollback snapshot port | Turnover primary builders/local connection no longer accept broad pair service; guard requires the explicit port. |
| `SettingsDataResetPairSnapshotPort` | explicit settings reset snapshot/save port | Settings reset service no longer accepts broad pair service; guard requires snapshot port injection. |
| ETC `persist_pair_relations` callbacks | explicit post-command persist boundary | Previous slice classified these callbacks after proving command-service writes are required and direct pair fallback is guarded. |
| runtime worker local pair snapshot construction | runtime projection support | Worker builds local `WorkbenchPairRelationService` snapshot from state store for matching/projection execution and command repository callback persistence; not a page/service fallback write path. |
| `PostgresWorkbenchRelationRepository` and state stores | canonical persistence/repository surfaces | Repository/state store methods own SQL/local snapshot load/save and are allowed to reference `app.workbench_pair_relations`. |
| repair/migration tools | explicit operational tooling | Tool references are CLI repair/migration surfaces with dry-run/apply semantics or canonical state store/repository access; they are not page/runtime legacy fallback paths. |
| tests/static guards | verification only | Remaining references in tests are expected guard strings or fixtures. |

## Decision

Mark this slice as `production-evidence-deferred`, with module closure `not-module-closed`.

This means:

- local `workbench_relation` implementation support slices are currently accounted for;
- no additional local implementation slice is required before choosing the next non-Go modular IO boundary;
- the full `workbench_relation` module is not closed;
- Go/Fiber/Go Worker candidates remain blocked.

## Production Evidence Still Missing

The remaining gap is environment evidence that cannot be proven in the current local setup without staging/local PostgreSQL or controlled production validation:

- real PostgreSQL relation table/history replay evidence;
- worker dirty/outbox/readiness drain evidence;
- App Status production relation readiness evidence;
- high-row relation distribution and active generation performance evidence;
- browser smoke over production-like data;
- rollback evidence under real worker/process topology.

Because these are real environment evidence gaps, they are recorded as `production-evidence-deferred` rather than silently passed.

## Go Admission Decision

Go admission stays blocked.

The current slice does not satisfy the Go gates in `11-GO-HOT-PATH-CARVE-OUT.md`:

- no performance baseline was collected;
- no shadow-run plan was executed;
- no Python-vs-Go equivalence evidence exists;
- no Go rollback gate exists;
- no candidate-specific IO/admission file was produced.

The next executable boundary must be non-Go. The queue should select the next read model/modular IO pilot before any Go hot-path candidate.

## Next Boundary

Insert and select:

`read-models:next-pilot-selection-after-workbench-relation`

This is an analysis/planning boundary to choose the next safe module based on the existing read model manifest, roadmap, module docs and remaining high-risk cross-page freshness chains.

## State Machine Impact

No state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:final-local-implementation-closure-and-production-evidence-defer`
- Previous status: `pending`
- New status: `production-evidence-deferred`
- Module closure: `not-module-closed`
- Next queue item: `read-models:next-pilot-selection-after-workbench-relation`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business behavior changed.
2. Service-layer tests: existing service and static guard tests are evidence; no runtime code changed in this slice.
3. API contract tests: not applicable; no API changed.
4. Read model/cache/background job tests: not applicable for this accounting-only slice; production worker/readiness evidence remains deferred.
5. Frontend component and interaction tests: not applicable; no frontend changed.
6. End-to-end business-flow integration tests: not applicable locally for this accounting-only slice; production-like browser/worker smoke remains deferred.
7. Existing feature regression tests: existing workbench relation guard/test inventory remains the protection evidence.

## Verification

Required verification:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this final local closure/defer accounting slice is complete. `workbench_relation` is not globally closed, and Go hot-path admission remains blocked.
