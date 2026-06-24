# Read Model Closure Wave 1 W4 Handoff - Cost Statistics / Tax Offset

**Worker:** W4
**Scope:** `cost_statistics` / `tax_offset`
**handoff_status:** `completed-local-evidence-handoff`
**closure:** `closure-not-claimed`
**Base commit before handoff write:** `cfc495f19af507e34c16a9991c421d37a4263b23`
**Head commit if changed:** final W4 docs commit reported by worker final response; the commit hash is not embedded here to avoid a self-referential amend loop.
**Production mutation:** none
**Secrets read:** none

## Files Changed

- `.planning/refactors/modular-io-boundaries/parallel/handoffs/read-model-closure-wave1-cost-tax.md`

## Controller-Only Files Touched

none

## Evidence Read

- `AGENTS.md`
- `docs/modules/README.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/tests.md`
- `docs/modules/cost-statistics/state-machine.md`
- `docs/modules/cost-statistics/e2e-coverage.md`
- `docs/modules/tax-offset/README.md`
- `docs/modules/tax-offset/tests.md`
- `docs/modules/tax-offset/state-machine.md`
- `docs/modules/tax-offset/e2e-coverage.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
- `.planning/refactors/modular-io-boundaries/12-PARALLEL-ORCHESTRATION.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/cost_statistics_read_model_repository.py`
- `backend/src/fin_ops_platform/services/cost_statistics_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/cost_statistics_runtime_service.py`
- `backend/src/fin_ops_platform/services/cost_statistics_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/services/tax_offset_read_model_repository.py`
- `backend/src/fin_ops_platform/services/tax_offset_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/tax_offset_runtime_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_worker_rebuild_executor.py`
- `backend/src/fin_ops_platform/services/tax_offset_cache_warmup_executor.py`
- `backend/src/fin_ops_platform/services/tax_offset_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
- `backend/src/fin_ops_platform/app/routes_tax.py`
- Matching local test and browser inventories under `tests/test_cost_statistics*`, `tests/test_tax_offset*`, `web/src/test/*CostStatistics*`, `web/src/test/*Tax*`, `web/e2e/cost-statistics-*.spec.ts`, `web/e2e/tax-offset-flow.spec.ts`, and `web/e2e/workbench-relations-tax-offset-fanout.spec.ts`.

## Local Evidence Map

### `cost_statistics`

- Repository port evidence: `CostStatisticsReadModelRepositoryPort` exposes only `load_cost_statistics_read_models`, `get_cost_statistics_view`, and `save_cost_statistics_read_models`, keeping the read-model repository surface narrow.
- Manifest and worker ownership evidence: `READ_MODEL_MANIFEST["cost_statistics"]` records primary worker `cost-statistics`, auxiliary compat lane `cost-tax`, projection strategy `partitioned_scoped_parent_rollup`, `all_scope_semantics=queryable_parent_aggregate`, query owner `CostStatisticsQueryService`, permission owner `cost_statistics_api_session`, and repository owner `PostgresReadModelRepository.cost_statistics`.
- Scope contract evidence: `read_model_scope_policy.py` delegates `cost_statistics` normalization and validation to `CostStatisticsRuntimeService`, supporting `active:YYYY-MM`, `all:YYYY-MM`, `active:all`, and `all:all`; legacy bare month / bare `all` can only pass through gateway normalization.
- Fresh gate/source-version evidence: `CostStatisticsRuntimeService.expected_source_versions(...)` and schema/source hashed Redis keys support expected source-version contracts; docs and tests require `ReadModelQueryGateway` or equivalent expected source/schema proof before fresh payloads can be returned.
- Worker fan-out and parent aggregate evidence: `CostStatisticsReadModelRefreshService` rebuilds month shards, then enqueues the same project-scope parent; parent scope checks missing/stale shards, returns `refreshing` while waiting, and only publishes parent fresh after shard convergence.
- Operation barrier evidence: cost statistics has downstream browser/API coverage for write-driven fan-out paths from Workbench relation, ETC import, no-OA submit, turnover manual closure, and settings project-scope changes; local docs still treat real operation-to-fresh latency as production/staging evidence.
- API/browser local evidence: `tests/test_cost_statistics_api.py`, `tests/test_cost_statistics_sql_runtime.py`, `tests/test_cost_statistics_read_model_service.py`, `tests/test_cost_statistics_runtime_service.py`, `tests/test_cost_statistics_derived_lifecycle_executor.py`, `tests/test_read_model_refresh_gateway.py`, `tests/test_runtime_worker_read_model_refresh_scopes.py`, `tests/test_read_model_manifest.py`, `web/src/test/CostStatisticsApi.test.ts`, `web/src/test/CostStatisticsPage.test.tsx`, `web/e2e/cost-statistics-flow.spec.ts`, and `web/e2e/cost-statistics-relation-fanout.spec.ts`.

### `tax_offset`

- Repository port evidence: `TaxOffsetReadModelRepositoryPort` exposes only `load_tax_offset_read_models`, `get_tax_offset_view`, and `save_tax_offset_read_models`, keeping the read-model repository surface narrow.
- Manifest and worker ownership evidence: `READ_MODEL_MANIFEST["tax_offset"]` records primary worker `tax-offset`, auxiliary compat lane `cost-tax`, projection strategy `partitioned_scoped_incremental`, `all_scope_semantics=fan_out_command`, query owner `TaxOffsetQueryService`, permission owner `tax_offset_api_session`, and repository owner `PostgresReadModelRepository.tax_offset`.
- Scope/fresh gate evidence: `TaxOffsetRuntimeService.request_scope_key(...)` accepts month scopes only; `expected_source_versions()` and schema/source hashed Redis keys support expected source-version proof for fresh month and summary payloads.
- Worker fan-out evidence: `TaxOffsetReadModelRefreshService` treats `all` as a fan-out command, enumerates month shards through the projection builder, enqueues each shard through `ReadModelRefreshGateway.enqueue_many("tax_offset", ...)`, and completes the `all` dirty scope without writing a fake month payload.
- Cache warmup/runtime executor evidence: `TaxOffsetCacheWarmupExecutor` covers env-gated background warmup, idempotent job creation, progress, partial failure accounting, read-model upsert and persistence. `TaxOffsetWorkerRebuildExecutor` rebuilds a month scope, persists the read model snapshot, and publishes fresh Redis month/summary cache envelopes after source-version/schema proof is available.
- Derived lifecycle evidence: `TaxOffsetDerivedLifecycleExecutor` separates read-model invalidation from month-cache clearing and routes scope keys through `TaxOffsetRuntimeService`.
- Operation barrier evidence: `web/src/test/TaxOffsetPage.test.tsx` covers waiting for `/api/operation-barrier/status` after plan save before reloading; `web/e2e/workbench-relations-tax-offset-fanout.spec.ts` checks Workbench relation fan-out and operation barrier polling.
- API/browser local evidence: `tests/test_tax_offset_api.py`, `tests/test_tax_offset_sql_runtime.py`, `tests/test_tax_offset_read_model_service.py`, `tests/test_tax_offset_worker_rebuild_executor.py`, `tests/test_tax_offset_cache_warmup_executor.py`, `tests/test_tax_offset_derived_lifecycle_executor.py`, `tests/test_read_model_refresh_gateway.py`, `tests/test_runtime_worker_read_model_refresh_scopes.py`, `tests/test_read_model_manifest.py`, `web/src/test/TaxApi.test.ts`, `web/src/test/TaxOffsetPage.test.tsx`, `web/e2e/tax-offset-flow.spec.ts`, and `web/e2e/workbench-relations-tax-offset-fanout.spec.ts`.

## Production Baseline Attachment

These row245/row246 facts are attached as baseline evidence only. They do not prove authenticated API response shape, browser rendering, operation-barrier behavior, high-row safety, export/detail behavior, or module/global closure.

### `cost_statistics`

- Row245 production matrix: `cost_statistics` readiness fresh for 66 scopes; dirty scopes done; outbox done; `cost_statistics.read_model.refresh` outbox rows done; `cost-statistics-read-model` and compat `cost-tax-read-model` heartbeats were current and idle; read-model tables were queryable with 68 `cost_statistics_read_models` and 8705 `cost_statistics_rows`.
- Row246 scope-contract classification: scope-contract dry-run returned `ok=true`, `violation_count=0`, no current uncovered outbox failures, no invalid policy-managed read-model scopes; legacy `cost` rows were historical `done` dirty-scope rows only, with no active outbox/readiness residue.

### `tax_offset`

- Row245 production matrix: `tax_offset` readiness fresh for 19 scopes; dirty scopes done; outbox done; `tax_offset.read_model.refresh` outbox rows done; `tax-offset-read-model` and compat `cost-tax-read-model` heartbeats were current and idle; read-model tables were queryable with 18 `tax_offset_read_models` and 793 `tax_offset_items`.
- Row246 scope-contract classification: scope-contract dry-run returned `ok=true`, `invalid_scope_count=0`; legacy `tax` rows were historical `done` dirty-scope rows only, with no active outbox/readiness residue.

## Remaining Gaps

### `cost_statistics`

- Authenticated production-style API response-shape sweep for explorer, month summary, export-preview, export, transaction detail and project scope fields.
- Parent aggregate/source-version proof against production data: verify `active:all` / `all:all` parent freshness comes from materialized shard rows and current source versions, not Workbench `all` payload or stale cache.
- High-row browser proof against production-like volume: first screen, 390px/narrow wide-table scroll, drilldown, export center, and large-row interaction safety.
- Relation fan-out proof in production-style conditions: Workbench relation, ETC import, no-OA submit, turnover manual closure and settings project-scope changes should be tied to worker drain/App Status/readiness evidence.
- Real Redis/RabbitMQ/systemd worker drain and operation-to-fresh latency remain production/staging evidence, not local closure evidence.

### `tax_offset`

- Authenticated production-style `/api/tax-offset`, summary, calculate, plan save, certified import preview/confirm/job, and permission/session response-shape sweep.
- Cache warmup/runtime executor proof in real runtime: env gate, background job, Redis fresh month/summary cache, partial failure accounting and source-version/schema envelope.
- Browser proof against production-like data: first screen, nonfresh states, permission states, 390px large-table interaction, certified drawer, save/import flows and stale conflict recovery.
- Workbench relation fan-out proof in production-style conditions: relation confirm should be tied to `tax_offset` dirty/outbox/readiness, operation barrier and fresh page reload evidence.
- Real tax-offset worker drain and App Status convergence remain production/staging evidence, not local closure evidence.

## Proposed T0 Follow-Up

- Run or schedule authenticated read-only API shape smoke for cost statistics and tax offset using production-safe session tooling without printing cookies, tokens or secrets.
- Collect production read-only source-version/readiness samples for `cost_statistics` parent scopes, cost month shards, `tax_offset` month scopes, Redis/cache status if available through non-secret endpoints, and worker heartbeat/drain status.
- Run browser smoke for cost statistics first-screen/high-row/export/detail/relation fan-out and tax offset first-screen/nonfresh/permission/save/import/relation fan-out. Classify results as browser smoke evidence, not closure until T0 accepts them.
- If a gap is found, assign a follow-up implementation worker within the affected module ownership. W4 does not recommend changing controller-only files or production state from this handoff.

## Seven Test Category Assessment

| Category | Applicability | W4 decision |
| --- | --- | --- |
| 1. Business core unit tests | Applicable | Existing cost/tax service tests cover cost attribution, project scope, tax calculation, certified import and plan selection. No code changed, so no new tests added. |
| 2. Service-layer tests | Applicable | Existing read-model service, runtime service, cache warmup, worker rebuild, derived lifecycle and API service tests cover local service contracts. No code changed, so no new tests added. |
| 3. API contract tests | Applicable | Existing backend API, frontend API mapper and browser specs cover local response contracts. Authenticated production-style API sweep remains a gap. |
| 4. Read model/cache/background job tests | Applicable | Existing SQL runtime, query/refresh gateway, worker scope, manifest and cache warmup tests cover local boundaries. Real Redis/RabbitMQ/systemd drain remains a gap. |
| 5. Frontend component and interaction tests | Applicable | Existing Vitest and Playwright specs cover local user-observable states. Production-like high-row/browser smoke remains a gap. |
| 6. End-to-end business-flow integration tests | Applicable | Existing browser and backend flows cover Workbench relation/import/no-OA/turnover/settings fan-out locally. Production operation-to-fresh evidence remains a gap. |
| 7. Existing feature regression tests | Applicable | Existing module regression libraries cover historical cost/tax bugs. No code changed, so no new regression tests added. |

## Verification Run

- `bash scripts/verify.sh docs`: passed.
- `git diff --check`: passed.

## Handoff Conclusion

本 handoff 只整理 Cost Statistics / Tax Offset 的本地实现、测试、文档和生产 baseline 证据。row245/row246 只能作为当前生产 read-model runtime baseline 和 legacy `cost` / `tax` 历史 done 分类，不能证明认证 API shape、浏览器行为、真实 worker drain、operation barrier 或 high-row/export/detail closure。

`closure-not-claimed`
