# Read Model Cost Statistics Post-Full-State Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:cost-statistics-post-full-state-local-implementation-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Previous State

`read-models:cost-statistics-full-state-read-model-snapshot-quarantine` removed the last known broad full-state write path: `Application._persist_state(...)` no longer serializes `cost_statistics_read_models`.

Before this audit, local cost statistics support already had:

- `CostStatisticsReadModelRepositoryPort` for manifest-listed load/get/save.
- SQL query and projection save paths routed through the repository port.
- SQL fresh gate through `ReadModelQueryGateway`.
- Production SQL repository unavailable behavior returning refreshing/enqueue instead of synchronous rebuild.
- Scope policy normalization for `active:YYYY-MM`, `all:YYYY-MM`, `active:all`, `all:all` and legacy bare month/all inputs.
- Queryable parent aggregate behavior from materialized month shards.
- Primary `cost-statistics` worker plus `cost-tax` compatibility lane classification.
- `CostStatisticsDerivedLifecycleExecutor` for derived lifecycle invalidation/fallback/job accounting.
- Runtime-owned warmup/retry/rebuild behavior through `CostStatisticsRuntimeService`.
- Explicit `_persist_cost_statistics_read_models_best_effort(...)` for runtime/query persistence.

## Audit Method

Inspected:

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `backend/src/fin_ops_platform/services/cost_statistics_runtime_service.py`
- `backend/src/fin_ops_platform/services/cost_statistics_query_service.py`
- `backend/src/fin_ops_platform/services/cost_statistics_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/services/cost_statistics_read_model_repository.py`
- `backend/src/fin_ops_platform/services/cost_tax_sql_projection.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`
- `tests/test_read_model_architecture_guards.py`
- `tests/test_platform_runtime_boundary_guards.py`

Used CodeGraph to inspect the cost statistics derived lifecycle/runtime boundary, then used literal search for `cost_statistics_read_models`, `cost_statistics.read_model.refresh`, `job.outbox_events`, `job.read_model_dirty_scopes`, Redis cache publish helpers, worker rebuild methods and route-owned cost statistics wrappers.

## Local Closure Findings

No remaining local implementation gap was found after full-state snapshot quarantine.

| Surface | Classification | Evidence |
| --- | --- | --- |
| `Application._persist_state(...)` | removed old broad full-state write path | Static guard proves it no longer serializes `cost_statistics_read_models` or calls `_cost_statistics_read_model_service.snapshot()`. |
| `Application._persist_cost_statistics_read_models_best_effort(...)` | explicit persistence boundary | Kept as dependency injected into `CostStatisticsRuntimeService` and `CostStatisticsQueryService`; it calls state-store `save_cost_statistics_read_models(...)` only. |
| Cost statistics startup `from_snapshot(...)` | local compatibility read path | Preserved; not a write path and not a production closure claim. |
| `Application._handle_api_cost_statistics*` / `_get_*_cost_statistics_*` | route/dependency compatibility delegates | Delegate to `CostStatisticsApiRoutes` or `CostStatisticsQueryService`; no business rules, SQL, dirty/outbox or cache publish ownership. |
| `Application.rebuild_cost_statistics_read_model_scope(...)` | worker compatibility delegate | Delegates to `CostStatisticsRuntimeService.rebuild_read_model_scope(scope_key)`. |
| `Application._invalidate_cost_statistics_*` / `_enqueue_cost_statistics_refresh_for_months(...)` | compatibility delegates | Delegate to `CostStatisticsRuntimeService`, which uses `ReadModelRefreshGateway` for non-transactional enqueue. |
| `Application._schedule_cost_statistics_cache_warmup(...)` / `_run_cost_statistics_cache_warmup_job(...)` | compatibility delegates | Delegate to `CostStatisticsRuntimeService`; no app-owned payload rebuild or read model upsert remains. |
| `CostStatisticsRuntimeService` | explicit runtime owner | Owns cache invalidation, warmup job orchestration, gateway enqueue and local compatibility rebuild using injected dependencies. |
| `CostStatisticsQueryService` | explicit query owner | Uses `ReadModelQueryGateway`; production SQL runtime repository miss returns refreshing/enqueue. Local non-SQL fallback remains compatibility behavior, not production closure evidence. |
| `CostStatisticsSqlProjectionBuilder` | projection/rebuild owner | Saves through `CostStatisticsReadModelRepositoryPort`; parent aggregate remains materialized-shard based. |
| `ReadModelRefreshGateway` / scope policy | shared enqueue boundary | Cost statistics enqueue paths normalize/validate through the gateway/scope policy for non-transactional refresh. |
| Worker/App Status/manifest registry | registered | `cost_statistics` exists in manifest, App Status registry, runtime worker registry and worker handler wiring. |

## Deferred Evidence

The following are still not proven in this local run and remain deferred:

- Real PostgreSQL `read_model.cost_statistics_read_models` / row table state after deployment.
- Real `job.outbox_events` and `job.read_model_dirty_scopes` drain for `cost_statistics.read_model.refresh`.
- Real App Status scope readiness after high-impact upstream writes.
- High-row production SLO for cost statistics parent and month scopes.
- Browser smoke against real authenticated production data.
- Production legacy scope cleanup / repair apply evidence.

This defer is explicit and does not mean `cost_statistics` is globally closed.

## State Machine Impact

- `read-models:cost-statistics-post-full-state-local-implementation-closure-audit` transitions to `production-evidence-deferred`.
- `cost_statistics` module closure remains `not-module-closed`.
- Insert `read-models:next-pilot-selection-after-cost-statistics` as the next pending boundary before Go candidates.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `production-evidence-deferred` semantics.
- `docs/modules/cost-statistics/state-machine.md` definitions do not change; no cost statistics business/UI/read model/worker state transition changed.

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not applicable. No cost attribution, amount, project scope, permission, relation or export business rule changed. |
| 2. Service-layer tests | Applicable by evidence reuse; cost statistics runtime/query/derived lifecycle tests cover explicit service ownership and persistence callbacks. |
| 3. API contract tests | Not applicable for this audit slice. No route or response shape changed. |
| 4. Read model/cache/background job tests | Applicable by evidence reuse; SQL runtime, runtime service, derived lifecycle and architecture guard tests cover freshness, cache and full-state quarantine boundaries. |
| 5. Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Deferred to production/browser evidence; this audit made no behavior change. |
| 7. Existing feature regression tests | Applicable by evidence reuse; cost statistics SQL/runtime/derived lifecycle and architecture guard tests protect old behavior while preventing old broad full-state contamination from returning. |

## Verification

Run for this audit:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_cost_and_tax_read_models_are_not_written_by_broad_full_state_persist -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_runtime_service tests.test_cost_statistics_derived_lifecycle_executor tests.test_cost_statistics_sql_runtime -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- This slice does not provide real production PostgreSQL/worker/App Status/high-row/browser evidence.
- The module is not globally closed.
- Go summary-rollup admission remains blocked until all prerequisite modular IO/read model boundaries and performance evidence are available.

## Next Boundary

`read-models:next-pilot-selection-after-cost-statistics`
