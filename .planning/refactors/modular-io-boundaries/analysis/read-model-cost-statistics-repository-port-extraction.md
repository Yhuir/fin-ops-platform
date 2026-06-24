# Read Model Cost Statistics Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:cost-statistics-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`cost_statistics` was selected as the ninth non-Go read model implementation pilot because it has high cross-page stale-read risk, special `active/all` scope grammar, queryable parent aggregate semantics, an old `cost-tax` compatibility worker lane and a narrow repository-port first slice.

Before this slice, `read_model_manifest.py` already listed the cost statistics repository port contract, but `CostStatisticsSqlProjectionBuilder` still accepted and default-created the broad `PostgresReadModelRepository` directly. `PostgresStateStore.cost_statistics_sql_read_repository` also returned the broad shared repository.

## Selected Boundary

Extract a narrow `CostStatisticsReadModelRepositoryPort` and wire cost statistics read/projection persistence paths through it without changing behavior.

## Implementation Evidence

Added `backend/src/fin_ops_platform/services/cost_statistics_read_model_repository.py`:

- `CostStatisticsReadModelRepositoryPort.load_cost_statistics_read_models(...)`;
- `CostStatisticsReadModelRepositoryPort.get_cost_statistics_view(...)`;
- `CostStatisticsReadModelRepositoryPort.save_cost_statistics_read_models(...)`.

Updated `backend/src/fin_ops_platform/services/cost_tax_sql_projection.py`:

- `CostStatisticsSqlProjectionBuilder` now wraps the provided repository, or the default `PostgresReadModelRepository(connection)`, in `CostStatisticsReadModelRepositoryPort`.
- `_publish_cost_statistics_scope(...)` continues to call `save_cost_statistics_read_models(...)` through the narrow port.
- SQL table knowledge and source fact queries remain in existing repository/projection owners; no business behavior changed.

Updated `backend/src/fin_ops_platform/services/postgres_state_store.py`:

- Added `_cost_statistics_sql_read_repository = CostStatisticsReadModelRepositoryPort(self._sql_read_model_repository)`.
- `cost_statistics_sql_read_repository` now returns the port over the optional SQL read connection.
- Existing write-side `save_cost_statistics_read_models(...)` still uses the write repository and local snapshot compatibility path.

Updated tests:

- `CostStatisticsReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods` proves the port exposes cost statistics load/get/save and does not expose tax offset, turnover or search methods.
- `PostgresStateStoreTests.test_read_model_repositories_use_optional_read_connection` now verifies the cost statistics SQL read port uses the optional read connection.
- Existing SQL projection parent/month tests continue to pass through the wrapped port.

## Legacy / Pollution Classification

| Surface | Classification | Decision |
| --- | --- | --- |
| `CostStatisticsSqlProjectionBuilder` broad repository constructor parameter | narrowed | It still accepts compatible repository objects for tests/default construction, but stores only `CostStatisticsReadModelRepositoryPort`. |
| `PostgresStateStore.cost_statistics_sql_read_repository` returning broad repository | removed | It now returns `CostStatisticsReadModelRepositoryPort`. |
| `PostgresReadModelRepository` SQL owner | retained | SQL/table knowledge remains here; splitting SQL tables is out of scope. |
| `cost-tax` compatibility worker | unchanged compatibility lane | Still registered as auxiliary worker; primary owner remains `cost-statistics`. |
| API/route/runtime wrappers | unchanged | No HTTP shape, permission, audit, Redis, queue or operation barrier behavior changed. |

## State Machine Impact

- `read-models:cost-statistics-repository-port-extraction` transitions to `implementation-closed`.
- `cost_statistics` remains `implementation-gap-open`; repository port extraction is only the first implementation slice.
- Insert next boundary: `read-models:cost-statistics-refresh-freshness-operation-barrier-audit`.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- State-machine definitions do not change; this uses existing `implementation-closed` semantics.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No cost attribution, project scope, amount, relation eligibility or export business rule changed. |
| 2. Service-layer tests | Applicable | Added repository port guard and state-store read-connection wiring regression. |
| 3. API contract tests | Existing regression applies | No HTTP shape changed; existing cost statistics SQL/API tests remain the contract surface. |
| 4. Read model/cache/background job tests | Applicable | Targeted SQL projection tests prove month/parent rebuild still saves through the port; existing SQL runtime tests remain the broader suite. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this slice | No runtime flow or business chain behavior changed. |
| 7. Existing feature regression tests | Applicable | Existing cost statistics projection parent aggregate and state-store optional read connection tests were run. |

## Verification

Initial targeted verification passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/cost_statistics_read_model_repository.py backend/src/fin_ops_platform/services/cost_tax_sql_projection.py backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_cost_statistics_sql_runtime.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_sql_runtime.CostStatisticsReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts tests.test_cost_statistics_sql_runtime.CostStatisticsSqlRuntimeTests.test_cost_statistics_sql_projection_rebuilds_active_all_from_materialized_shard_rows tests.test_postgres_state_store.PostgresStateStoreTests.test_read_model_repositories_use_optional_read_connection -v
```

Final verification must include broader targeted SQL runtime tests, app check, docs verification and diff checks before commit.

## Next Boundary

`read-models:cost-statistics-refresh-freshness-operation-barrier-audit`

Audit cost statistics freshness, force refresh, queryable parent aggregate, operation barrier, compatibility worker and remaining app-owned helper surfaces before any Go summary-rollup admission.
