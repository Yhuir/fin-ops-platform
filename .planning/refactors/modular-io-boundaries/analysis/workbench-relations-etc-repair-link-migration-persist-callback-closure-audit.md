# Workbench Relations - ETC Repair Link Migration Persist Callback Closure Audit

**Date:** 2026-06-24
**Boundary:** `workbench-relations:etc-repair-link-migration-persist-callback-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit ETC repair/link/migration `persist_pair_relations` callbacks and decide whether they are removable, an explicit post-command persist boundary, compat-only test/tool wiring, or an implementation gap requiring a port.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-local-implementation-closure-and-production-evidence-defer.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/services/historical_etc_repair_service.py`
- `backend/src/fin_ops_platform/services/historical_etc_business_batch_migration_service.py`
- `backend/src/fin_ops_platform/services/existing_etc_batch_link_service.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/tools/migrate_historical_etc_business_batches.py`
- `backend/src/fin_ops_platform/tools/link_existing_etc_batches.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_etc_backend.py`
- `tests/test_historical_etc_business_batch_migration_service.py`

## Findings

The ETC repair/link/migration services do not keep a direct pair relation write fallback:

- `HistoricalEtcRepairService` requires `relation_command_service.confirm_relation(...)` before local ETC writes.
- `HistoricalEtcBusinessBatchMigrationService` requires `relation_command_service.update_relation_metadata_for_case_id(...)` before local ETC writes.
- `ExistingEtcBatchLinkService` requires `relation_command_service.update_relation_metadata_for_case_id(...)` before local ETC writes.
- Existing tests verify the services fail fast when command service is missing, instead of falling back to broad pair service writes.
- Static guard `test_etc_repair_and_link_services_do_not_keep_direct_relation_write_fallbacks` rejects `pair_relation_service` / `_pair_relation_service` in those services and requires command-boundary methods.

The `persist_pair_relations` callbacks are still required in the current in-memory/local runtime shape. They run after command-service relation updates to persist changed relation case IDs through the existing relation persist boundary. This is a post-command persistence side-effect, not the relation write owner.

## Decision

Classify ETC repair/link/migration `persist_pair_relations` callbacks as an explicit post-command persist boundary.

No implementation slice is required before closure/defer accounting.

The next boundary should retry final local implementation closure and production evidence defer accounting:

`workbench-relations:final-local-implementation-closure-and-production-evidence-defer`

Go hot-path candidates remain blocked until that accounting proves prerequisites are met or explicitly deferred.

## Legacy Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| `HistoricalEtcRepairService.persist_pair_relations` | explicit post-command persist boundary | Relation write goes through command service; callback persists changed case IDs after command success. |
| `HistoricalEtcBusinessBatchMigrationService.persist_pair_relations` | explicit post-command persist boundary | Metadata update goes through command service; callback persists changed case IDs after command success. |
| `ExistingEtcBatchLinkService.persist_pair_relations` | explicit post-command persist boundary | Metadata update goes through command service; callback persists changed case IDs after command success. |
| Direct pair relation fallback in ETC services | removed/guarded | Static guard rejects pair service dependencies and tests require fail-fast without command service. |
| ETC tools injecting app persist callback | tool wiring for explicit boundary | Tools use app command service plus app persist boundary; no direct pair service mutation fallback identified. |

## State Machine Impact

No global or module state definition changed.

The state transition is slice-only:

- Previous queue item: `workbench-relations:etc-repair-link-migration-persist-callback-closure-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `workbench-relations:final-local-implementation-closure-and-production-evidence-defer`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business behavior changed.
2. Service-layer tests: existing ETC service tests identified as evidence; no code changed.
3. API contract tests: not applicable; no API changed.
4. Read model/cache/background job tests: not applicable; no runtime behavior changed.
5. Frontend component and interaction tests: not applicable.
6. End-to-end business-flow integration tests: not applicable for this audit-only slice.
7. Existing feature regression tests: existing ETC tests and static guard protect the audited boundary.

## Verification

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only this ETC callback audit slice is closed. `workbench_relation` remains `implementation-gap-open` until final local closure/defer accounting is completed.
