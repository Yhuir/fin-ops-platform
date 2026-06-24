# Read Model No-OA Bank Batch Full-State Snapshot Quarantine

**Date:** 2026-06-24
**Boundary:** `read-models:no-oa-bank-batch-full-state-snapshot-quarantine`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Remove broad `Application._persist_state(...)` writes of no-OA bank batch snapshots while preserving explicit no-OA mutation and worker refresh persistence boundaries.

## Implementation

- Removed `"no_oa_bank_batches": self._no_oa_bank_batch_service.snapshot()` from `Application._persist_state(...)`.
- Added `ReadModelArchitectureGuardTests.test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist`.
- The guard proves broad full-state persistence no longer serializes no-OA batch snapshots and that explicit no-OA persistence boundaries remain available:
  - `NoOaBankBatchReadModelPersistencePort`
  - `ApplicationStateStore.save_no_oa_bank_batch_mutation(...)`
  - `PostgresStateStore.save_no_oa_bank_batch_mutation(...)`

## Contract

No-OA persistence must use explicit boundaries:

- Mutation persistence: `save_no_oa_bank_batch_mutation(...)`.
- Worker refresh public snapshot persistence: `NoOaBankBatchReadModelPersistencePort.save_public_snapshot(...)`.
- PostgreSQL SQL/table ownership remains in the existing repository/state-store path behind those explicit boundaries.

Broad `_persist_state(...)` is no longer allowed to persist `no_oa_bank_batches` or snapshot `self._no_oa_bank_batch_service`.

## Preserved Behavior

- No business lifecycle, API response, worker event, queue schema, Redis/cache behavior, permission, audit meaning or frontend behavior changed.
- Explicit no-OA submit/withdraw/tag-selection and worker refresh persistence paths remain intact.
- Local/Mongo compatibility is preserved through explicit state-store boundaries and existing bootstrap load behavior.

## State Machine Impact

- `read-models:no-oa-bank-batch-full-state-snapshot-quarantine` transitions to `implementation-closed`.
- `no_oa_bank_batch` remains `implementation-gap-open` until a post-full-state local closure audit re-checks current code.
- The next boundary is `read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit`.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No no-OA lifecycle, relation, amount, status or validation rule changed. |
| 2. Service-layer tests | Applicable as evidence | Existing no-OA application service tests protect explicit mutation behavior; no service behavior changed. |
| 3. API contract tests | Not directly applicable | No HTTP route, status code, response shape or permission behavior changed. |
| 4. Read model/cache/background job tests | Applicable | Added architecture guard for no-OA broad full-state snapshot quarantine and reran no-OA/read-model regression tests. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior or operation barrier target changed. |
| 6. End-to-end business-flow integration tests | Not directly applicable | No user flow changed; existing no-OA Workbench integration regression was rerun. |
| 7. Existing feature regression tests | Applicable | Guard prevents the old broad full-state no-OA snapshot writer from returning. |

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/no_oa_bank_batch_application_service.py backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_mutation_persistence_requires_atomic_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_read_model_refresh_does_not_run_relation_repairs tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_list_read_model_uses_repository_port tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_derived_lifecycle_uses_explicit_executor_boundary -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_workbench_integration tests.test_read_model_manifest tests.test_read_model_refresh_gateway tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_no_oa_bank_batches_are_not_written_by_broad_full_state_persist -v
bash scripts/verify.sh docs
git diff --check
```
