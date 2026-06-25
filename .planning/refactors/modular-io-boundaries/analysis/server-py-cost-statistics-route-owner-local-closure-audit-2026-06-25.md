# server-py:cost-statistics-route-owner-local-closure-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit remaining cost statistics `Application` surfaces after `/api/cost-statistics*` route callback collapse.

This is a local `server.py` boundary audit. It does not claim cost statistics module closure, global modular IO closure, or production PostgreSQL/worker/browser evidence closure.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/state-machine.md`
- `docs/modules/cost-statistics/tests.md`
- `analysis/server-py-cost-statistics-route-owner-audit-2026-06-25.md`
- `analysis/server-py-cost-statistics-route-callback-collapse-2026-06-25.md`

Commands used for the local audit:

```bash
PYTHONPATH=backend/src python3 - <<'PY'
import ast
from pathlib import Path
p=Path("backend/src/fin_ops_platform/app/server.py")
t=ast.parse(p.read_text())
for n in sorted((n for n in ast.walk(t) if isinstance(n,(ast.FunctionDef, ast.AsyncFunctionDef)) and "cost_statistics" in n.name.lower()), key=lambda n:n.lineno):
    print(f"{n.lineno}:{n.name}")
PY
rg -n "_handle_api_cost_statistics|CostStatisticsApiRoutes|_cost_statistics_routes|rebuild_cost_statistics|_invalidate_cost_statistics|_schedule_cost_statistics|_run_cost_statistics|_cost_statistics_" backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
```

## Remaining Cost Statistics `Application` Surface

| Surface | Classification | Evidence |
| --- | --- | --- |
| `_configure_cost_statistics_application_services(...)`, `_ensure_cost_statistics_application_services(...)`, `_cost_statistics_routes(...)`, `_cost_statistics_runtime(...)`, `_cost_statistics_query(...)` | dependency assembly / route-owner factory | These wire `CostStatisticsApiRoutes`, `CostStatisticsQueryService` and `CostStatisticsRuntimeService` through explicit dependencies. They do not own cost HTTP mapping after Row376. |
| `_get_or_build_cost_statistics_explorer(...)`, `_get_cost_statistics_explorer_from_sql_read_model(...)`, `_get_cost_statistics_month_from_sql_read_model(...)`, `_cost_statistics_month_payload_from_explorer_payload(...)` | query compatibility/provider delegates | These delegate to `CostStatisticsQueryService` and remain for local/runtime compatibility seams. They do not perform route response mapping. |
| `_cost_statistics_expected_source_versions(...)`, `_cost_statistics_source_versions(...)`, `_cost_statistics_*_redis_cache_key(...)`, `_cost_statistics_redis_ttl_seconds(...)`, `_empty_cost_statistics_*_payload(...)`, `_cost_statistics_explorer_entry_count(...)` | runtime/source-version/cache provider ports | These delegate to `CostStatisticsRuntimeService` or `CostStatisticsQueryService` and are consumed by query/runtime/worker paths. |
| `_persist_cost_statistics_read_models_best_effort(...)` | explicit read-model persistence port | Explicit persistence remains available for runtime/query paths after broad full-state snapshot persistence was quarantined in the earlier cost statistics read-model slice. |
| `_emit_cost_statistics_explorer_metric(...)`, `_cost_statistics_file_response(...)` | HTTP/platform adapter ports | Metric emission and XLSX response construction are platform concerns injected into the route owner. |
| `_cost_statistics_scope_keys_for_import_preview(...)`, `_cost_statistics_scope_keys_for_import_file_session(...)`, `_cost_statistics_scope_keys_for_import_rows(...)` | import scope adapter ports | Thin scope extraction adapters translating import rows into cost statistics refresh scopes. |
| `rebuild_cost_statistics_read_model_scope(...)`, `_cost_statistics_derived_lifecycle_executor(...)`, `_invalidate_cost_statistics_*`, `_enqueue_cost_statistics_refresh_for_months(...)`, `_delete_cost_statistics_redis_cache(...)` | worker/derived lifecycle/refresh delegate ports | These route behavior through `CostStatisticsRuntimeService`, `CostStatisticsDerivedLifecycleExecutor` and gateway-backed refresh helpers. |
| `_retry_cost_statistics_*`, `_recover_interrupted_cost_statistics_cache_warmup_jobs(...)`, `_find_reusable_cost_statistics_warmup_job(...)`, `_schedule_cost_statistics_cache_warmup(...)`, `_run_cost_statistics_cache_warmup_job(...)`, `_normalize_cost_statistics_scope_keys(...)`, `_parse_cost_statistics_scope_key(...)`, `_cost_statistics_warmup_result_summary(...)` | cache warmup compatibility delegates | Prior cost statistics read-model closure accounting classified warmup/retry/rebuild app methods as runtime delegates. |

## Findings

- No `_handle_api_cost_statistics*` callback remains in `server.py`.
- `CostStatisticsApiRoutes.route(...)` now owns `/api/cost-statistics*` route dispatch and query parsing.
- Remaining cost statistics methods in `Application` are explicit composition-root, query/runtime, source-version, persistence, cache, worker, warmup, import-scope or platform adapter ports.
- Cost statistics local `server.py` route-owner support is accounted for, but cost statistics full module closure is not claimed because production PostgreSQL/worker/App Status/high-row/browser/admin/write evidence remains final-validation scope.

## Decision

Cost statistics route-owner local support is accounted for after:

- Row375 route owner audit;
- Row376 route callback collapse;
- prior repository port, SQL fresh gate, parent aggregate, worker registry, derived lifecycle executor, runtime warmup/retry/rebuild owner and full-state snapshot quarantine slices;
- static guards preventing route callback and derived lifecycle regressions.

The next local-first boundary should move to turnover ledger route ownership. `TurnoverLedgerApiRoutes` exists, but `Application` still owns many `/api/turnover-ledger*` dispatch branches and `_handle_api_turnover_ledger*` callbacks, including read/export/tag/extra/confirm/withdraw surfaces.

## Next Boundary

`server-py:turnover-ledger-route-owner-audit`

## Stop Gates For Next Boundary

- Do not change turnover ledger behavior during the audit.
- Do not weaken stale preconditions, operation barrier targets, Workbench relation command boundaries, export limits or `turnover_ledger` freshness semantics.
- Do not claim turnover ledger module/global closure from route-owner accounting alone.
- Do not run production validation or mutation.
