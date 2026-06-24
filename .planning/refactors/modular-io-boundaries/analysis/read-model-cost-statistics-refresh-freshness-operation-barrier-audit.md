# Read Model Cost Statistics Refresh Freshness Operation Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:cost-statistics-refresh-freshness-operation-barrier-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`cost_statistics` repository port extraction is complete. `CostStatisticsReadModelRepositoryPort` owns the manifest-listed load/get/save surface, PostgreSQL state-store SQL read wiring returns that port, and `CostStatisticsSqlProjectionBuilder` persists through the port.

The module is still not locally closed. Repository port extraction did not audit freshness, operation barrier, parent aggregate, compatibility worker, derived lifecycle or old app-owned helper surfaces.

## Selected Boundary

Audit cost statistics freshness and operation-barrier local support after repository port extraction. If a concrete local implementation gap exists, insert the next narrow implementation boundary before Go candidates.

## Evidence Reviewed

- `.planning/ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/prompts/04-master-goal-controller.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-tax-offset.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-tax-ledger-summary-contract.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/state-machine.md`
- `docs/modules/cost-statistics/tests.md`
- CodeGraph context/explore for `CostStatisticsReadModelRefreshService`, `CostStatisticsSqlProjectionBuilder`, `CostStatisticsQueryService`, `ReadModelRefreshGateway`, and `OperationFreshnessBarrierService`.
- Focused source review of `cost_statistics_runtime_service.py`, `routes_cost_statistics.py`, `server.py`, `worker.py`, `runtime_worker_registry.py`, `runtime_worker_handlers.py`, `read_model_scope_policy.py`, `app_status_read_model_registry.py`, and relevant tests.

## Audit Findings

| Area | Evidence | Decision |
| --- | --- | --- |
| SQL fresh gate | `CostStatisticsQueryService.get_explorer_from_sql_read_model(...)` and `get_month_from_sql_read_model(...)` both call `ReadModelQueryGateway.load(...)` with expected schema/source versions, Redis cache key, SQL view loader and miss/stale/source mismatch reasons. `tests/test_cost_statistics_sql_runtime.py` covers Redis cache, SQL miss, malformed payload and production SQL repository unavailable behavior. | Locally supported. |
| Production repository unavailable | In production SQL runtime, `CostStatisticsQueryService.get_explorer(...)` returns `read_model_status=refreshing`, `error=read_model_unavailable`, and enqueues through `CostStatisticsRuntimeService.enqueue_read_model_refresh(...)` when SQL repository is unavailable. | Locally supported for explorer. Existing month summary behavior is covered by SQL miss tests and no new gap was found in this audit. |
| Scope policy / force refresh | `ReadModelScopePolicyRegistry` registers special `cost_statistics` policy. Legacy bare months and bare `all` normalize to `active/all` project-scope shards; invalid project scopes are rejected before durable queue enqueue. | Locally supported. |
| Month shard semantics | `CostStatisticsSqlProjectionBuilder.rebuild_cost_statistics_month_scope(...)` publishes `active:YYYY-MM` / `all:YYYY-MM`; refresh service re-enqueues the matching parent scope after month convergence. | Locally supported. |
| Parent aggregate semantics | `rebuild_cost_statistics_parent_scope(...)` uses materialized shard rows and records `cost_statistics_parent_source=materialized_shards`; `CostStatisticsReadModelRefreshService._handle_parent_scope(...)` returns `readiness_status=refreshing` and does not complete dirty scope while shards are missing/stale. | Locally supported. |
| Redis cache | `ReadModelQueryGateway` is the read cache fresh gate; runtime/projection cache writes build fresh envelopes only from newly generated payloads. Existing architecture guard classifies these direct fresh cache writers. | Locally supported with existing guard coverage. |
| Worker ownership | `runtime_worker_registry.py` declares primary `cost-statistics` worker and auxiliary `cost-tax` compatibility lane. `app_status_read_model_registry.py` points operation/readiness ownership at `cost-statistics`. | Locally supported; compatibility lane remains. |
| Operation barrier | `APP_STATUS_READ_MODEL_REGISTRY` registers `cost_statistics`, so the generic `OperationFreshnessBarrierService` can resolve cost statistics targets from runtime readiness/outbox facts. Cost statistics has no direct write UI; write-after-read relevance comes from upstream modules and page fresh gates/E2E flows. | No direct local code gap found for a cost-statistics-specific barrier endpoint. |
| App-owned derived lifecycle | `Application._derived_lifecycle_cost_statistics_executor(...)` still owns cost statistics derived lifecycle invalidation/warmup-vs-refresh fallback and `enqueued_jobs` accounting. This differs from recently extracted `BankDetailDerivedLifecycleExecutor`, `WorkbenchRelationDerivedLifecycleExecutor`, `InvoiceLifecycleDerivedLifecycleExecutor`, and `TaxOffsetDerivedLifecycleExecutor` patterns. | Local implementation gap. Extract next. |
| App-owned warmup/retry wrappers | `Application._schedule_cost_statistics_cache_warmup(...)`, `_run_cost_statistics_cache_warmup_job(...)`, retry/remaining-scope helpers, scope parsing and cache helpers are thin delegates to `CostStatisticsRuntimeService`, but they remain app-owned compatibility wrappers used by tests and background-job route glue. | Do not remove in this audit. Reassess after derived lifecycle executor extraction. |
| Broad full-state snapshot | `tests/test_read_model_architecture_guards.py::test_tax_offset_read_models_are_not_written_by_broad_full_state_persist` currently asserts `cost_statistics_read_models` remains in `_persist_state(...)`, unlike tax offset. | Not selected for immediate next slice because derived lifecycle still owns behavior in `Application`; full-state snapshot quarantine may follow after executor/warmup wrapper closure. |

## Next Implementation Boundary

`read-models:cost-statistics-derived-lifecycle-executor-port-extraction`

Expected scope:

- Add a `CostStatisticsDerivedLifecycleExecutor` service.
- Move the behavior currently owned by `Application._derived_lifecycle_cost_statistics_executor(...)` behind that executor:
  - derive scope keys from lifecycle domain plan;
  - preserve `pending_invoice_rules_changed` `persist_empty` behavior;
  - call cost statistics runtime invalidation APIs;
  - preserve `schedule_warmup=False` generic refresh fallback and metadata propagation;
  - preserve `enqueued_jobs` accounting.
- Keep `Application` as dependency assembly and a thin delegate only.
- Add/update tests proving the old app-owned lifecycle executor logic cannot re-own the behavior.
- Do not change cost attribution, API shape, Redis key/envelope, worker event names, queue schema, parent aggregate semantics or frontend behavior.

## Legacy / Pollution Classification

| Surface | Classification | Owner | Deletion / follow-up condition | Forbidden writes |
| --- | --- | --- | --- | --- |
| `Application._derived_lifecycle_cost_statistics_executor(...)` | local implementation gap | currently `Application`; should move to `CostStatisticsDerivedLifecycleExecutor` | next boundary | Must not directly own dirty/outbox/cache/readiness semantics after extraction. |
| `Application._schedule_cost_statistics_cache_warmup(...)` | compat-only thin delegate | `CostStatisticsRuntimeService` | reassess after derived lifecycle extraction | Must not directly create jobs or write read models outside runtime service. |
| `Application._run_cost_statistics_cache_warmup_job(...)` | compat-only thin delegate | `CostStatisticsRuntimeService` | reassess after derived lifecycle extraction | Must not directly upsert read models or cache payloads outside runtime service. |
| `Application.rebuild_cost_statistics_read_model_scope(...)` | worker compat delegate | `CostStatisticsRuntimeService` for local/runtime path; SQL worker path uses `CostStatisticsSqlProjectionBuilder` | reassess in later worker/cache warmup audit | Must not bypass runtime/projection owners. |
| `cost-tax` worker lane | compatibility lane | `runtime_worker_registry.py` auxiliary worker | keep until production worker migration plan retires combined lane | Must not become sole owner or change primary worker ownership. |

## State Machine Impact

- `read-models:cost-statistics-refresh-freshness-operation-barrier-audit` transitions to `analysis-closed`.
- `cost_statistics` remains `implementation-gap-open`.
- Insert `read-models:cost-statistics-derived-lifecycle-executor-port-extraction` as the next pending boundary before Go candidates.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `analysis-closed` semantics.
- `docs/modules/cost-statistics/state-machine.md` definitions do not change; the audit confirms current rules and identifies an implementation ownership gap.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable for this audit | No cost attribution, project scope, amount, relation eligibility or export business rule changed. |
| 2. Service-layer tests | Applicable as evidence | Existing query/runtime/gateway/service tests prove current boundaries; next executor slice must add focused service/static tests. |
| 3. API contract tests | Existing regression applies | No HTTP behavior changed; existing cost statistics API/SQL runtime tests remain relevant evidence. |
| 4. Read model/cache/background job tests | Applicable | Existing SQL runtime, refresh gateway, runtime worker scope and App Status tests cover freshness, parent aggregate and queue behavior. |
| 5. Frontend component and interaction tests | Not applicable for this audit | No frontend behavior changed. Existing page/e2e coverage remains downstream evidence. |
| 6. End-to-end business-flow integration tests | Not applicable for this audit | No runtime business flow changed. Existing e2e evidence informs risk. |
| 7. Existing feature regression tests | Applicable | Re-run targeted cost statistics/read model tests and docs verification before commit. |

## Verification

Required for this analysis/accounting slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime tests.test_read_model_refresh_gateway tests.test_runtime_worker_read_model_refresh_scopes -v
PYTHONPATH=backend/src python3 -m unittest tests.test_operation_freshness_barrier tests.test_read_model_architecture_guards -v
bash scripts/verify.sh docs
git diff --check
```

## Next Boundary

`read-models:cost-statistics-derived-lifecycle-executor-port-extraction`
