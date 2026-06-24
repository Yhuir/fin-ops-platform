# Read Model Cost Statistics Derived Lifecycle Executor Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:cost-statistics-derived-lifecycle-executor-port-extraction`
**Previous state:** `read-models:cost-statistics-refresh-freshness-operation-barrier-audit` was `analysis-closed`.
**Result state:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Scope

Extract the app-owned cost statistics derived lifecycle executor into an explicit service boundary while preserving existing invalidation, warmup-vs-refresh fallback, metadata propagation and result-shape behavior.

This slice does not change cost attribution, project scope, export behavior, parent aggregate semantics, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning, API shape, frontend behavior, Go/Fiber or Go Worker behavior.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/implementation-notes.md`
- `docs/modules/cost-statistics/state-machine.md`
- `docs/modules/cost-statistics/tests.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/cost_statistics_runtime_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/services/invoice_lifecycle_derived_lifecycle_executor.py`
- `tests/test_tax_offset_derived_lifecycle_executor.py`
- `tests/test_invoice_lifecycle_derived_lifecycle_executor.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph was used before edits to inspect adjacent derived lifecycle executor patterns and the cost statistics runtime service dependency surface.

## Implementation

Runtime code:

- Added `backend/src/fin_ops_platform/services/cost_statistics_derived_lifecycle_executor.py`.
- `CostStatisticsDerivedLifecycleExecutor.execute(...)` now owns:
  - domain-plan scope trimming/filtering;
  - default reason `derived_lifecycle_cost_statistics`;
  - `pending_invoice_rules_changed` `persist_empty=False` behavior;
  - full invalidation for `all` scopes through `CostStatisticsRuntimeService.invalidate_read_models(...)`;
  - explicit-scope invalidation through `CostStatisticsRuntimeService.invalidate_read_model_scopes(...)`;
  - `schedule_warmup=False` generic refresh fallback through the injected refresh producer;
  - allowed metadata propagation for generic refresh enqueue;
  - existing `deleted_counts`, `invalidated_scopes` and `enqueued_jobs` return shape.
- `Application` now builds `CostStatisticsDerivedLifecycleExecutor` with explicit dependencies:
  - `runtime_service=self._cost_statistics_runtime()`;
  - a gateway-backed generic refresh callback for `cost_statistics`;
  - a `ReadModelRefreshGateway.can_enqueue()` capability callback.
- The derived lifecycle registry now calls `self._cost_statistics_derived_lifecycle_executor().execute(...)`.
- Removed `Application._derived_lifecycle_cost_statistics_executor(...)`.

Tests:

- Added `tests/test_cost_statistics_derived_lifecycle_executor.py` covering:
  - explicit scope invalidation and gateway refresh job accounting;
  - `schedule_warmup=False` refresh fallback metadata and deleted-scope shape;
  - `pending_invoice_rules_changed` `persist_empty=False`;
  - `all` scope full invalidation and cache warmup job accounting when the gateway is unavailable;
  - empty-scope no-warmup fallback to `all`.
- Updated `tests/test_platform_runtime_boundary_guards.py` to prove:
  - the old app-owned helper is removed;
  - `server.py` builds the explicit cost statistics executor;
  - the lifecycle registry uses the executor;
  - the executor preserves key behavior snippets.

## Legacy / Pollution Classification

| Surface | Classification | Result |
| --- | --- | --- |
| `Application._derived_lifecycle_cost_statistics_executor(...)` | removed app-owned implementation logic | Replaced by `CostStatisticsDerivedLifecycleExecutor`. |
| `Application._cost_statistics_derived_lifecycle_executor(...)` | dependency assembly | Builds the explicit executor and injects runtime/gateway callbacks. |
| `_enqueue_generic_read_model_refreshes("cost_statistics", ...)` | retained gateway-backed refresh producer callback | Still uses `ReadModelRefreshGateway` and scope policy registry before durable queue enqueue. |
| `CostStatisticsRuntimeService.invalidate_read_models(...)` / `invalidate_read_model_scopes(...)` | retained runtime owner | Continues to own cache invalidation, read model invalidation and warmup scheduling behavior. |
| Derived lifecycle domain map | migrated | `cost_statistics_read_model` points to the explicit executor. |

No path touched in this slice writes canonical facts, dirty scopes, outbox events, readiness, cache, App Status or new authoritative outputs outside the existing runtime/gateway boundaries.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/cost-statistics/state-machine.md`

No global or module state definition changed. This slice changes implementation ownership only.

Transition:

- `read-models:cost-statistics-derived-lifecycle-executor-port-extraction`: `pending` -> `implementation-closed`
- `cost_statistics` remains `implementation-gap-open`
- Next queue item: `read-models:cost-statistics-post-derived-local-implementation-closure-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not applicable. No cost attribution, project scope, amount rule, relation eligibility, permission rule or export business rule changed. |
| 2. Service-layer tests | Covered by `tests.test_cost_statistics_derived_lifecycle_executor`. |
| 3. API contract tests | Not applicable. No HTTP route, status code, response shape or permission behavior changed. |
| 4. Read model/cache/background job tests | Covered by executor tests, cost statistics runtime tests and cost statistics SQL runtime regressions. |
| 5. Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not required for this narrow ownership move; real worker drain remains production evidence/defer scope. |
| 7. Existing feature regression tests | Covered by cost statistics SQL/runtime regressions and platform boundary guard. |

## Verification

Ran:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/cost_statistics_derived_lifecycle_executor.py backend/src/fin_ops_platform/app/server.py tests/test_cost_statistics_derived_lifecycle_executor.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_derived_lifecycle_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_cost_statistics_derived_lifecycle_uses_explicit_executor_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_runtime_service tests.test_cost_statistics_derived_lifecycle_executor tests.test_cost_statistics_sql_runtime -v
```

Attempted broader guard:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards tests.test_read_model_architecture_guards -v
```

The broader guard still fails on two unrelated pre-existing platform guard findings outside this slice:

- `backend/src/fin_ops_platform/tools/repair_submitted_etc_invoice_overlaps.py` contains direct `update app.invoices` SQL.
- `backend/src/fin_ops_platform/tools/oa_attachment_invoice_promotion.py` passes `allow_create` to OA attachment invoice upsert, and the existing server promotion guard does not find the expected `CREATE_INVOICE_AND_LINK` expression.

Final app/docs/diff verification is recorded in the commit that closes this slice.

## Remaining Risk

- Real PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable without production validation.
- This slice does not prove full local closure of `cost_statistics`; a post-derived local implementation closure audit is required next.
- App-owned cost statistics warmup/retry compatibility wrappers and broad full-state snapshot behavior were not changed in this slice.
- `cost_statistics` is not globally closed.

## Next Boundary

`read-models:cost-statistics-post-derived-local-implementation-closure-audit`
