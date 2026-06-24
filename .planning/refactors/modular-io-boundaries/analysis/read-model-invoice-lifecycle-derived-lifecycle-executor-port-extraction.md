# Read Model Invoice Lifecycle Derived Lifecycle Executor Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction`
**Previous state:** `read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit` was `regression-guard-closed`.
**Result state:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Scope

Extract the app-owned invoice lifecycle derived lifecycle executor into an explicit service/port while preserving existing enqueue behavior.

This slice does not change invoice lifecycle business rules, payload shape, source-version semantics, worker event semantics, queue schema, API behavior, frontend behavior, Go/Fiber, Go Worker or production state.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-repository-port-extraction.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/domain-events-lifecycle/README.md`
- `docs/modules/domain-events-lifecycle/tests.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/bank_detail_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/services/workbench_relation_derived_lifecycle_executor.py`
- `tests/test_bank_detail_derived_lifecycle_executor.py`
- `tests/test_workbench_relation_derived_lifecycle_executor.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph was used before edits to inspect the app-owned invoice lifecycle executor, the derived lifecycle domain map, adjacent explicit executor patterns and guard tests.

## Implementation

Added `InvoiceLifecycleDerivedLifecycleExecutor` with the existing invoice lifecycle behavior:

- trims and filters `domain_plan["scope_keys"]`
- defaults target scopes to `["all"]` when none are present
- preserves reason default `derived_lifecycle_invoice_lifecycle`
- forwards only allowed refresh metadata keys and trims non-empty `action_name`
- returns the same `deleted_counts`, `invalidated_scopes` and `enqueued_jobs` payload shape

Wiring changes:

- `Application` now builds `InvoiceLifecycleDerivedLifecycleExecutor` with an `enqueue_refresh` callback.
- The callback still delegates to `_enqueue_generic_read_model_refreshes("invoice_lifecycle", ...)`, which uses `ReadModelRefreshGateway` and the scope policy registry before durable queue enqueue.
- The derived lifecycle domain map now calls `self._invoice_lifecycle_derived_lifecycle_executor().execute`.
- Removed `Application._derived_lifecycle_invoice_lifecycle_executor(...)`.

## Legacy / Pollution Classification

| Surface | Classification | Result |
| --- | --- | --- |
| `Application._derived_lifecycle_invoice_lifecycle_executor(...)` | removed app-owned implementation logic | Replaced by `InvoiceLifecycleDerivedLifecycleExecutor`. |
| `Application._invoice_lifecycle_derived_lifecycle_executor(...)` | dependency assembly | Builds the explicit executor and injects a gateway-backed refresh callback. |
| `_enqueue_generic_read_model_refreshes("invoice_lifecycle", ...)` | retained gateway-backed refresh producer callback | Still uses `ReadModelRefreshGateway`; no direct SQL dirty/outbox writes. |
| Derived lifecycle domain map | migrated | `invoice_lifecycle_read_model` points to the explicit executor. |

No old path in this slice writes canonical facts, dirty scopes, outbox events, readiness, cache, App Status or new authoritative outputs outside the gateway-backed refresh boundary.

## State-Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/domain-events-lifecycle/state-machine.md`

No workflow, module, business, read model or worker state definition changed. This slice advances one queue item:

- `read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction`: `pending` -> `implementation-closed`
- Module closure remains `implementation-gap-open`
- Next boundary becomes `read-models:invoice-lifecycle-local-implementation-closure-audit`
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`

## Seven Test Categories

1. Business core unit tests: not applicable. No lifecycle mapping, status rule, amount rule, permission rule or state transition changed.
2. Service-layer tests: applicable and covered by `tests/test_invoice_lifecycle_derived_lifecycle_executor.py`.
3. API contract tests: not applicable. No HTTP route, response shape, status code or permission behavior changed.
4. Read model/cache/background job tests: applicable and covered by executor enqueue-shape tests plus invoice lifecycle refresh/operation barrier regressions.
5. Frontend component and interaction tests: not applicable. No frontend behavior changed.
6. End-to-end business-flow integration tests: not required for this narrow extraction; `tests/test_derived_data_lifecycle_service.py` continues to cover lifecycle plan/domain ordering.
7. Existing feature regression tests: applicable and covered by derived lifecycle service, operation barrier, invoice lifecycle refresh and platform boundary guard tests.

## Verification

Ran:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/invoice_lifecycle_derived_lifecycle_executor.py backend/src/fin_ops_platform/app/server.py tests/test_invoice_lifecycle_derived_lifecycle_executor.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_lifecycle_derived_lifecycle_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_invoice_lifecycle_derived_lifecycle_uses_explicit_executor_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_relation_derived_lifecycle_uses_explicit_executor_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_detail_server_read_cache_helpers_stay_on_application_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service tests.test_workbench_relation_derived_lifecycle_executor tests.test_bank_detail_derived_lifecycle_executor tests.test_operation_freshness_barrier tests.test_invoice_lifecycle_read_model_refresh -v
```

Additional app/docs/diff verification is recorded in the commit that closes this slice.

## Remaining Risk

- Real PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable without production validation.
- This slice does not prove full local closure of `invoice_lifecycle`; a closure audit is required next.
- `invoice_lifecycle` is not globally closed.

## Next Boundary

`read-models:invoice-lifecycle-local-implementation-closure-audit`
