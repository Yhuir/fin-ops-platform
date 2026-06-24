# Read Model No-OA Bank Batch Freshness Derived Lifecycle Boundary Audit

**Date:** 2026-06-24
**Boundary:** `read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

The no-OA pilot now has:

- `NoOaBankBatchReadModelPersistencePort` for worker refresh public snapshot persistence.
- `NoOaBankBatchReadModelRepositoryPort` for list/query SQL read model access.
- Manifest, scope policy, runtime worker and App Status registry entries for `no_oa_bank_batch`.

The remaining question is whether refresh enqueue, derived lifecycle, operation barrier, force refresh, dirty/outbox and app-owned helper surfaces are locally closed.

## Audit Evidence

### Refresh Enqueue

- `NoOaBankBatchApplicationService.enqueue_background_refresh(...)` builds `ReadModelRefreshGateway(queue_repository=...)` and calls `enqueue_many("no_oa_bank_batch", scope_keys, reason=...)`.
- `Application._enqueue_no_oa_bank_batch_read_model_refreshes(...)` uses `self._read_model_refresh_gateway().enqueue_many("no_oa_bank_batch", ...)`, normalizes scopes to `all` or `YYYY-MM`, and passes metadata.
- `tests/test_read_model_refresh_gateway.py::ReadModelRefreshGatewayTests::test_no_oa_bank_batch_policy_accepts_all_and_month_scopes_only` guards the scope policy.

### Read Model Status And Worker

- `read_model_manifest.py` declares `no_oa_bank_batch` as `self_managed_freshness`, `scoped_incremental`, `fan_out_command`, `gateway_force_refresh`, and `app_status_registry_target`.
- `runtime_worker_registry.py` registers `no-oa-bank-batch` for `no_oa_bank_batch.read_model.refresh`.
- `app_status_read_model_registry.py` and `app_status_domain_registry.py` connect the read model, worker, job type and `/no-oa-bank-batches` route.
- `NoOaBankBatchReadModelRefreshService.handle_runtime_event(...)` rejects wrong event/scope, skips stale source-version events, calls `refresh_batches(apply_relation_repairs=False, scope_key=...)`, persists through `NoOaBankBatchReadModelPersistencePort`, and completes the dirty scope.

### Operation Barrier

- Submit-selection, internal-transfer submit and withdraw frontend flows wait on `operationBarrierTargetsFromMonths("no_oa_bank_batch", affectedMonths, fallbackMonth)`.
- Tag selection save waits on `operationBarrierTargets("no_oa_bank_batch", ["all"])`.
- `OperationFreshnessBarrierService` resolves status from runtime snapshot readiness, outbox and worker facts; it does not mutate readiness or rebuild read models.

### Concrete Remaining Gaps

1. `Application._derived_lifecycle_no_oa_bank_batch_executor(...)` still owns no-OA derived lifecycle refresh target selection and enqueue result assembly in `server.py`.
   - This mirrors already-extracted patterns such as `BankDetailDerivedLifecycleExecutor` and `InvoiceLifecycleDerivedLifecycleExecutor`.
   - It should be moved to a narrow `NoOaBankBatchDerivedLifecycleExecutor` that receives an explicit enqueue callback.

2. `NoOaBankBatchApplicationService.persist_mutation(...)` still has a compatibility fallback that directly calls broad state-store methods when `save_no_oa_bank_batch_mutation(...)` is missing:
   - `save_workbench_pair_relations(...)`
   - `save_no_oa_bank_batches(...)`
   - `save_workbench_read_models(...)`
   The primary PostgreSQL path has an atomic boundary in `PostgresStateStore.save_no_oa_bank_batch_mutation(...)`, but the fallback remains an old broad write path and needs a separate quarantine/removal decision.

## Selected Next Boundary

First split implementation boundary:

`read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction`

Rationale:

- It is small and mirrors established local patterns.
- It removes app-owned derived lifecycle enqueue behavior from `server.py`.
- It does not change API shape, business rules, worker events, queue schema, Redis/cache, permissions, audit meaning or frontend behavior.

Second later boundary:

`read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine`

This should handle the broader state-store fallback semantics after the derived lifecycle executor is extracted.

## State Machine Impact

- `read-models:no-oa-bank-batch-freshness-derived-lifecycle-boundary-audit` transitions to `analysis-closed`.
- `no_oa_bank_batch` remains `implementation-gap-open`.
- Insert `read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` as the next pending implementation boundary.
- Insert `read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine` after the executor extraction.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `analysis-closed` semantics.
- `docs/modules/no-oa-bank-batches/state-machine.md` definitions do not change because no business state, UI state, read model status, worker event, queue transition, operation barrier state or force-refresh state changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No lifecycle, relation, amount, tag or status rule changed. |
| 2. Service-layer tests | Applicable for next implementation | Current audit relies on existing no-OA application service and derived lifecycle tests; executor extraction must add focused service/static guard coverage. |
| 3. API contract tests | Not applicable | No HTTP response shape, status code, error field or permission behavior changed. |
| 4. Read model/cache/background job tests | Applicable for next implementation | Existing refresh gateway, worker and App Status tests cover current behavior; executor extraction must preserve enqueue metadata/result shape. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior or operation barrier target changed. |
| 6. End-to-end business-flow integration tests | Not directly applicable | No submit/withdraw/import/user flow changed in this audit. |
| 7. Existing feature regression tests | Applicable | Next implementation should rerun no-OA application/read-model/workbench integration and relevant lifecycle tests. |

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_workbench_integration tests.test_read_model_manifest tests.test_read_model_refresh_gateway -v
bash scripts/verify.sh docs
git diff --check
```
