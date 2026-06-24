# Read Model No-OA Bank Batch Derived Lifecycle Executor Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Move no-OA bank batch derived lifecycle refresh target selection and enqueue result assembly out of `Application` and into a narrow service executor with an explicit enqueue dependency.

This slice does not change business rules, API response shape, read model scope policy, worker event names, queue schema, Redis/cache behavior, permissions, audit behavior, frontend behavior or Go/Fiber/Go Worker admission.

## Implementation

- Added `NoOaBankBatchDerivedLifecycleExecutor`.
- Wired `Application` derived lifecycle target map to call `self._no_oa_bank_batch_derived_lifecycle_executor().execute`.
- Removed the app-owned `Application._derived_lifecycle_no_oa_bank_batch_executor(...)` helper.
- Kept `Application._enqueue_no_oa_bank_batch_read_model_refreshes(...)` as the app-level dependency assembly callback that delegates to `ReadModelRefreshGateway`.

## Preserved Contract

- Month-bearing lifecycle scopes still become sorted concrete month target scopes.
- Empty or non-month lifecycle scopes still fan out to `all`.
- Default reason remains `derived_lifecycle_no_oa_bank_batch`.
- Metadata forwarding still keeps the read model refresh metadata subset: `source`, `case_id`, `action_name`, `downstream_scope_types`, `invoice_usage_scope_types`, and `pending_invoice_scope_keys`.
- Result shape remains:
  - `deleted_counts.no_oa_bank_batch_read_models`
  - `invalidated_scopes`
  - `enqueued_jobs`

## Legacy Path Classification

- Removed: `Application._derived_lifecycle_no_oa_bank_batch_executor(...)` as an authoritative behavior owner.
- Retained dependency assembly: `Application._no_oa_bank_batch_derived_lifecycle_executor(...)` creates the explicit executor and passes the no-OA refresh enqueue callback.
- Still open: `NoOaBankBatchApplicationService.persist_mutation(...)` broad state-store fallback when `save_no_oa_bank_batch_mutation(...)` is absent.

## State Machine Impact

- `read-models:no-oa-bank-batch-derived-lifecycle-executor-port-extraction` transitions to `implementation-closed`.
- `no_oa_bank_batch` remains `implementation-gap-open`.
- Next boundary is `read-models:no-oa-bank-batch-mutation-persistence-fallback-quarantine`.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change.
- `docs/modules/no-oa-bank-batches/state-machine.md` definitions do not change because no business state, UI state, read model status, worker event, queue transition, operation barrier state or force-refresh state changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No lifecycle business rule, relation rule, amount rule, tag rule or status transition changed. |
| 2. Service-layer tests | Applicable | Added `tests/test_no_oa_bank_batch_derived_lifecycle_executor.py` for scope selection, reason defaults, metadata forwarding and result shape. |
| 3. API contract tests | Not applicable | No HTTP route, response shape, status code, error field or permission behavior changed. |
| 4. Read model/cache/background job tests | Applicable | Executor tests and platform guard protect read model refresh enqueue target semantics; existing no-OA/read model tests are rerun. |
| 5. Frontend component and interaction tests | Not applicable | Frontend operation barrier targets and UI behavior did not change. |
| 6. End-to-end business-flow integration tests | Not directly applicable | No import/submit/withdraw/browser flow changed; existing integration tests cover affected no-OA behavior. |
| 7. Existing feature regression tests | Applicable | Added platform guard proving derived lifecycle behavior stays outside `Application`; rerun no-OA application/read model/workbench and derived lifecycle regressions. |

## Verification

Passed:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/no_oa_bank_batch_derived_lifecycle_executor.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_derived_lifecycle_executor tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_derived_lifecycle_uses_explicit_executor_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_no_oa_bank_batch_application_service tests.test_no_oa_bank_batch_read_model_refresh tests.test_no_oa_bank_batch_workbench_integration tests.test_derived_data_lifecycle_service tests.test_read_model_manifest tests.test_read_model_refresh_gateway tests.test_no_oa_bank_batch_derived_lifecycle_executor tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_no_oa_bank_batch_derived_lifecycle_uses_explicit_executor_boundary -v
bash scripts/verify.sh docs
git diff --check
```
