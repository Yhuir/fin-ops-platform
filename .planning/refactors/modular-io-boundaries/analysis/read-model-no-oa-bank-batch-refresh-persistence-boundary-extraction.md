# Read Model No-OA Bank Batch Refresh Persistence Boundary Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`read-models:no-oa-bank-batch-repository-state-store-boundary-audit` found that no-OA registration contracts and route mapping are explicit, while `NoOaBankBatchReadModelRefreshService` still persisted `NoOaBankBatchService.public_snapshot()` directly through broad `state_store.save_no_oa_bank_batches(...)`.

The audit selected refresh persistence boundary extraction before list-only repository port extraction because the worker write path was the higher-risk stale-read and legacy-contamination surface.

## Selected Boundary

Extract a narrow no-OA read model refresh persistence boundary so the worker refresh handler no longer directly calls broad state-store persistence.

## Implementation

- Added `NoOaBankBatchReadModelPersistencePort` in `backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py`.
- The port exposes `save_public_snapshot(snapshot)` and delegates to the existing `save_no_oa_bank_batches(...)` capability.
- `NoOaBankBatchReadModelRefreshService` now accepts `read_model_persistence`.
- `handle_runtime_event(...)` now calls `self._read_model_persistence.save_public_snapshot(snapshot)` instead of `self._state_store.save_no_oa_bank_batches(snapshot)`.
- `backend/src/fin_ops_platform/app/worker.py` now explicitly wires `NoOaBankBatchReadModelPersistencePort(...)` into the no-OA worker refresh service.

## Preserved Behavior

- `NoOaBankBatchService.public_snapshot()` remains the public lifecycle projection source.
- `PostgresWorkbenchRepository.save_no_oa_bank_batches(...)` remains the SQL/table owner for `app.no_oa_bank_batches` and `read_model.no_oa_bank_batch_rows` cleanup/write behavior.
- `PostgresStateStore.save_no_oa_bank_batches(...)` remains available as the compatibility/delegation capability used by the adapter.
- Worker event type and scope type are unchanged.
- Stale source-version events still skip rebuild and do not overwrite read models.
- Month-scope refresh still reads only the target month and preserves other-month batches.
- The worker still passes `apply_relation_repairs=False` and does not persist Workbench relation mutations from the read model path.
- Queue dirty scope completion behavior is unchanged.
- API shape, frontend behavior, permissions, audit meaning, Redis/cache behavior and queue schema are unchanged.

## Tests Added Or Updated

- `tests/test_no_oa_bank_batch_read_model_refresh.py`
  - Added `test_persistence_port_delegates_to_store_snapshot_save`.
  - Added `test_refresh_persists_through_explicit_persistence_boundary`.
- `tests/test_platform_runtime_boundary_guards.py`
  - Strengthened `test_no_oa_read_model_refresh_does_not_run_relation_repairs` to require the persistence boundary and forbid direct `save_no_oa_bank_batches` calls in the refresh handler.

## State Machine Impact

- `read-models:no-oa-bank-batch-refresh-persistence-boundary-extraction` transitions to `implementation-closed`.
- `no_oa_bank_batch` remains `implementation-gap-open`; this is not module closure.
- Insert `read-models:no-oa-bank-batch-read-model-repository-port-extraction` as the next pending implementation boundary.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `implementation-closed` semantics.
- `docs/modules/no-oa-bank-batches/state-machine.md` definitions do not change because no business state, UI state, read model status, worker event, queue transition, operation barrier state or force-refresh state changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No lifecycle, relation, amount, tag or status rule changed. |
| 2. Service-layer tests | Applicable and covered | New tests cover the explicit persistence port and refresh handler dependency boundary. |
| 3. API contract tests | Not applicable | No HTTP response shape, status code, error field or permission behavior changed. Existing application/API regression tests were run through service/integration coverage. |
| 4. Read model/cache/background job tests | Applicable and covered | no-OA refresh tests cover persistence, stale source-version skip, month scope behavior, dependency non-fresh behavior and relation repair prohibition. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior or operation barrier target changed. |
| 6. End-to-end business-flow integration tests | Not directly applicable | No submit/withdraw/import/user flow changed; no-OA Workbench integration tests were run as regression coverage. |
| 7. Existing feature regression tests | Applicable and covered | no-OA application service and Workbench integration regressions were run. |

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_read_model_refresh.py backend/src/fin_ops_platform/app/worker.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_read_model_refresh_does_not_run_relation_repairs tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_workbench_integration -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

Also attempted:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_read_model_refresh tests.test_platform_runtime_boundary_guards -v
```

The full `tests.test_platform_runtime_boundary_guards` module failed on two unrelated existing OA invoice / ETC repair guard failures:

- `test_app_invoice_writes_stay_in_core_repository`
- `test_oa_attachment_invoice_create_permission_is_gated_by_recognition_service`

The no-OA guard added in this slice passed both in the full attempt and in targeted rerun.

## Next Boundary

`read-models:no-oa-bank-batch-read-model-repository-port-extraction`
