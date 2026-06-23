# Workbench Relations - Post Server Precondition Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:post-server-precondition-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Re-audit local `workbench_relation` implementation gaps after extracting the server repair/precondition read ports:

- `WorkbenchOaInvoiceOffsetRelationReadPort`
- `WorkbenchOaAttachmentRepairRelationReadPort`
- `WorkbenchConfirmLinkContextRelationReadPort`
- `WorkbenchAutoPairConflictRelationReadPort`

This is an analysis/accounting slice only. It must not mark the module closed from weak evidence and must not unblock Go hot-path admission prematurely.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-relation-read-helper-boundary-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-auto-pair-conflict-relation-read-port-extraction.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_persist_service.py`
- `backend/src/fin_ops_platform/services/workbench_pair_relation_rollback_restore_service.py`
- `backend/src/fin_ops_platform/services/workbench_exception_rollback_restore_service.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py`
- `backend/src/fin_ops_platform/services/no_oa_bank_batch_service.py`
- CodeGraph context for remaining relation persist/rollback/read facade surfaces.

## Findings

`workbench_relation` is still not module-closed.

Local implemented slices are substantial: repository/read model port, derived lifecycle executor, transaction persist repository owner split, command repository snapshot adapter, non-transactional persist service, rollback restore services, WorkbenchWriteFacade relation ports, matching relation read port, server payload/source-version/repair/precondition read ports, no-OA/pending/turnover cleanups and route/accounting delegations.

Remaining local gaps still exist:

| Surface | Current Classification | Notes |
| --- | --- | --- |
| `_supplemental_retained_oa_row_ids(...)` | next implementation boundary | Still directly calls `self._workbench_pair_relation_service.list_active_relations()` while computing retained OA rows for all-scope payload. |
| `_next_workbench_relation_case_id(...)` | later implementation boundary candidate | Still snapshots pair relations to avoid case id collisions. Needs explicit case-id allocation/read owner if kept in app. |
| `_persist_state(...)` whole app snapshot | later closure/quarantine accounting | Still serializes `workbench_pair_relations` as part of legacy full-state persistence. Needs compatibility classification before full closure. |
| `_persist_workbench_pair_relations_in_transaction(...)` | implemented but still app-owned assembly | Uses `PostgresWorkbenchRelationRepository`; direct snapshot read remains because transaction writer persists changed case snapshots. Needs later closure accounting or explicit snapshot port. |
| `WorkbenchPairRelationPersistService` | implemented service, not closure proof | Correctly owns non-transactional snapshot persist, but still depends on `WorkbenchPairRelationService` as the in-memory canonical fact holder. |
| `WorkbenchPairRelationRollbackRestoreService` and `WorkbenchExceptionRollbackRestoreService` | implemented rollback services | Required for failure recovery; not removable without a broader rollback design. |
| `WorkbenchWriteRelationReadSnapshotPort` / special metadata port | explicit port classes | These intentionally wrap pair service inside the write facade module. Existing guards prove facade no longer accepts broad pair service. |
| `NoOaPairRelationSnapshotPort` | explicit snapshot adapter | Still required for no-OA rollback/persist compatibility. |
| app bootstrap `WorkbenchPairRelationService.from_snapshot(...)` | canonical in-memory fact assembly | Expected while local runtime still supports in-memory/mongo-only mode. |
| `AppHealthAlertService` / route builders receiving pair service | later audit candidate | Needs focused owner/caller/deletion-condition classification before closure. |

## Decision

Do not mark `workbench_relation` as closed or production-evidence-deferred.

Do not run Go admission.

Queue the next narrow implementation boundary:

`workbench-relations:server-retained-oa-supplemental-relation-read-port-extraction`

This is smaller and safer than case-id allocation or whole-state persistence because it is a read-only payload support helper with a single direct `list_active_relations()` call and existing retained-OA context tests.

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:post-server-precondition-local-implementation-closure-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:server-retained-oa-supplemental-relation-read-port-extraction`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no behavior changed.
2. Service-layer tests: not applicable; no code changed.
3. API contract tests: not applicable; no HTTP contract changed.
4. Read model/cache/background job tests: not applicable; no runtime read model behavior changed.
5. Frontend component and interaction tests: not applicable; no frontend code changed.
6. End-to-end business-flow integration tests: not applicable for this analysis-only slice.
7. Existing feature regression tests: not run because this slice only records implementation gap accounting.

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this audit slice is closed. `workbench_relation` remains `implementation-gap-open`.
