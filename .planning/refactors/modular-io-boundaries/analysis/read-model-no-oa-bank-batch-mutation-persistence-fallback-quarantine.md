# Read Model No-OA Bank Batch Mutation Persistence Fallback Quarantine

**Date:** 2026-06-24
**Boundary:** `read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove the no-OA mutation persistence fallback in `NoOaBankBatchApplicationService.persist_mutation(...)` that directly called broad state-store write methods when the atomic mutation boundary was unavailable.

## Implementation

- `NoOaBankBatchApplicationService.persist_mutation(...)` now requires `save_no_oa_bank_batch_mutation(...)` and fails fast with `NoOaBankBatchPersistenceError` if the boundary is absent.
- Added `ApplicationStateStore.save_no_oa_bank_batch_mutation(...)` so local/Mongo state-store runtimes use the same explicit no-OA mutation boundary instead of relying on service-layer fallback writes.
- Existing `PostgresStateStore.save_no_oa_bank_batch_mutation(...)` remains the production SQL atomic boundary.
- Added service, state-store and static guard tests.

## Contract

The explicit no-OA mutation persistence boundary receives:

- `pair_relation_snapshot`
- `no_oa_bank_batch_snapshot`
- `workbench_read_model_snapshot`
- `changed_case_ids`
- `changed_scope_keys`

The service layer no longer calls these broad state-store methods directly from `persist_mutation(...)`:

- `save_workbench_pair_relations(...)`
- `save_no_oa_bank_batches(...)`
- `save_workbench_read_models(...)`

## Preserved Behavior

- no-OA submit/withdraw/internal-transfer mutation semantics are unchanged.
- `persist=False` still emits derived lifecycle events without persisting snapshots.
- Search cache clear still runs before the explicit mutation boundary.
- PostgreSQL production path continues to use `PostgresStateStore.save_no_oa_bank_batch_mutation(...)`.
- Local/Mongo compatibility is preserved by adding the same explicit boundary to `ApplicationStateStore`.

## State Machine Impact

- `read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine` transitions to `implementation-closed`.
- `no_oa_bank_batch` remains `implementation-gap-open` until a local implementation closure audit re-checks route/service/repository/read model/worker/frontend/API surfaces.
- Next boundary is `read-models:no-oa-bank-batch-local-implementation-closure-audit`.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change.
- `docs/modules/no-oa-bank-batches/state-machine.md` definitions do not change because no business state, UI state, read model status, worker event, queue transition, operation barrier state or force-refresh state changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No lifecycle, relation, amount, tag or status rule changed. |
| 2. Service-layer tests | Applicable | Added a no-OA application service fail-fast test for missing atomic boundary. |
| 3. API contract tests | Not directly applicable | No HTTP response shape, status code, error field or permission behavior changed. Existing API persistence error tests remain valid. |
| 4. Read model/cache/background job tests | Applicable | State-store mutation boundary test covers local persistence of pair relation, no-OA batch and Workbench read model snapshots through one explicit entrypoint. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior or operation barrier target changed. |
| 6. End-to-end business-flow integration tests | Not directly applicable | No submit/withdraw user-flow semantics changed; existing no-OA integration tests were rerun. |
| 7. Existing feature regression tests | Applicable | Added static guard preventing broad service-layer fallback writes from returning; reran no-OA application/read model/workbench and read model registry/gateway tests. |

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py backend/src/fin_ops_platform/services/state_store.py backend/src/fin_ops_platform/services/postgres_state_store.py
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service.NoOaBankBatchApplicationServiceTests.test_after_mutation_persists_changed_cases_and_expanded_workbench_scopes tests.test_no_oa_bank_batch_application_service.NoOaBankBatchApplicationServiceTests.test_after_mutation_without_atomic_persistence_boundary_fails_fast tests.test_state_store.StateStoreTests.test_save_no_oa_bank_batch_mutation_uses_explicit_local_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_mutation_persistence_requires_atomic_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_workbench_integration tests.test_state_store.StateStoreTests.test_save_no_oa_bank_batch_mutation_uses_explicit_local_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_mutation_persistence_requires_atomic_boundary tests.test_read_model_manifest tests.test_read_model_refresh_gateway -v
bash scripts/verify.sh docs
git diff --check
```
