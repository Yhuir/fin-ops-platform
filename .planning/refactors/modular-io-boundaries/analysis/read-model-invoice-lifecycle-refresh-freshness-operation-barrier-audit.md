# Read Model Invoice Lifecycle Refresh Freshness Operation Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit`
**Previous state:** `read-models:invoice-lifecycle-repository-port-extraction` was `implementation-closed`.
**Result state:** `regression-guard-closed`
**Module closure:** `implementation-gap-open`

## Scope

Audit invoice lifecycle read model freshness, force refresh, fan-out `all`, source-version proof, operation barrier behavior and legacy/live rebuild contamination after repository port extraction.

This slice adds one regression guard for operation barrier scope isolation. It does not change lifecycle rules, projection payloads, source-version semantics, worker event semantics, queue schema, API behavior, frontend behavior, Go/Fiber, Go Worker or production state.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-output-invoice-collection.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-and-usage-contract.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/domain-events-lifecycle/README.md`
- `docs/modules/domain-events-lifecycle/tests.md`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_read_facade.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_sql_projection.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_invoice_lifecycle_read_facade.py`
- `tests/test_invoice_lifecycle_read_model_refresh.py`
- `tests/test_operation_freshness_barrier.py`
- `tests/test_read_model_manifest.py`
- `tests/test_derived_data_lifecycle_service.py`
- `tests/test_workbench_dirty_queue_wiring.py`

CodeGraph was used before edits to inspect invoice lifecycle refresh, freshness, scope policy, operation barrier, worker and application helper surfaces.

## Audit Findings

### Freshness and query proof

- `InvoiceLifecycleReadFacade` is the query owner and now uses `InvoiceLifecycleReadModelRepositoryPort`.
- `get_by_subject_ids(...)` and `get_by_invoice_identity_keys(...)` do not query a parent `all` payload. They read materialized lifecycle rows by subject or identity key and return non-fresh when rows or repository methods are unavailable.
- `list_by_month(...)` requires a concrete month. There is no queryable `invoice_lifecycle:all` read path in this facade.
- Non-fresh facade paths enqueue through `ReadModelRefreshGateway`, so scope normalization/validation/dedupe remains centralized.

### Force refresh and fan-out `all`

- `read_model_scope_policy.py` registers `invoice_lifecycle` as month-or-all. Invalid `active:*` style scopes are rejected by shared gateway tests.
- `InvoiceLifecycleReadModelRefreshService` rejects Application fallback dependencies, validates `scope_type="invoice_lifecycle"`, checks source-version currentness before and after rebuild, and marks dirty scopes complete only after successful handling.
- `invoice_lifecycle:all` is treated as a fan-out command by `InvoiceLifecycleReadModelRefreshService`: non-month scopes list concrete month shards and enqueue those via `ReadModelRefreshGateway` with reason `invoice_lifecycle_month_shard`.
- If no shards exist, the projection builder can mark the provided scope empty. Because no queryable all read path exists, this does not currently provide a page all-query fresh proof. This behavior should remain visible in future closure accounting.

### Operation barrier

- Manifest and App Status registry already register `invoice_lifecycle` with `operation_barrier_contract="app_status_registry_target"`, scope type `invoice_lifecycle`, worker `invoice-lifecycle`, and event `invoice_lifecycle.read_model.refresh`.
- Added `tests/test_operation_freshness_barrier.py::OperationFreshnessBarrierServiceTests::test_invoice_lifecycle_target_uses_exact_month_scope_for_operation_barrier`.
- The new guard proves an operation barrier target for `invoice_lifecycle:2026-03` remains fresh even when another month `invoice_lifecycle:2026-04` has pending outbox, and the worker status resolves from the registry-backed `invoice-lifecycle` worker.

### Legacy and app-level helper classification

| Surface | Classification | Result |
| --- | --- | --- |
| `Application._enqueue_generic_read_model_refreshes("invoice_lifecycle", ...)` | gateway-backed app helper | Uses `ReadModelRefreshGateway`; no direct SQL dirty/outbox write. Retained as shared helper. |
| `Application._enqueue_input_invoice_usage_payment_rules_refreshes(...)` -> `invoice_lifecycle:all` | gateway-backed producer | Payment rules changes legitimately fan out lifecycle via `all`; no immediate runtime bug found. |
| `Application._derived_lifecycle_invoice_lifecycle_executor(...)` | implementation gap | Gateway-backed and safe, but still app-owned derived lifecycle executor logic. Should move to explicit `InvoiceLifecycleDerivedLifecycleExecutor` in the next slice. |
| Worker registration | closed for audit | `worker.py` builds `InvoiceLifecycleSqlProjectionBuilder` and `InvoiceLifecycleReadModelRefreshService`; refresh service rejects Application fallback. |
| State-store invoice lifecycle SQL read property | not-applicable | No existing caller exists; repository port extraction correctly avoided speculative state-store API. |

## State-Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/read-models/state-machine.md`
- `docs/modules/domain-events-lifecycle/state-machine.md`

No state definition changed. This slice advances one queue item:

- `read-models:invoice-lifecycle-refresh-freshness-operation-barrier-audit`: `pending` -> `regression-guard-closed`
- Module closure remains `implementation-gap-open`
- Next boundary becomes `read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction`
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`

## Seven Test Categories

1. Business core unit tests: not applicable. No lifecycle policy or status rule changed.
2. Service-layer tests: applicable as audit evidence. Existing refresh/facade tests cover refresh service and query boundary behavior.
3. API contract tests: not applicable. No HTTP shape, status code or permission behavior changed.
4. Read model/cache/background job tests: applicable and covered by invoice lifecycle refresh/facade/manifest tests plus the new operation barrier regression guard.
5. Frontend component and interaction tests: not applicable. No frontend behavior changed.
6. End-to-end business-flow integration tests: not applicable for this audit/guard slice. Cross-module derived lifecycle execution remains in the next boundary.
7. Existing feature regression tests: applicable and covered by targeted invoice lifecycle, manifest and operation barrier regression tests.

## Verification

Ran:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier tests.test_invoice_lifecycle_read_facade tests.test_invoice_lifecycle_read_model_refresh tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- Real PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable without production validation.
- `Application._derived_lifecycle_invoice_lifecycle_executor(...)` is gateway-backed but still app-owned; it remains the next local implementation gap.
- `invoice_lifecycle` is not globally closed.

## Next Boundary

`read-models:invoice-lifecycle-derived-lifecycle-executor-port-extraction`
