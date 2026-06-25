# server-py:tax-route-owner-local-closure-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit remaining tax offset and certified import `Application` surfaces after all tax HTTP route mapping was moved into `TaxApiRoutes.route(...)`.

This is a local `server.py` boundary audit. It does not claim tax module closure, global modular IO closure, or production PostgreSQL/worker/browser evidence closure.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_tax.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/tax-offset/README.md`
- `docs/modules/tax-offset/state-machine.md`
- `docs/modules/tax-offset/tests.md`
- `analysis/server-py-tax-route-owner-audit-2026-06-25.md`
- `analysis/server-py-tax-offset-read-plan-route-callback-collapse-2026-06-25.md`
- `analysis/server-py-tax-certified-import-route-callback-collapse-2026-06-25.md`

Commands used for the local audit:

```bash
PYTHONPATH=backend/src python3 - <<'PY'
import ast
from pathlib import Path
p=Path("backend/src/fin_ops_platform/app/server.py")
t=ast.parse(p.read_text())
for n in sorted((n for n in ast.walk(t) if isinstance(n,(ast.FunctionDef, ast.AsyncFunctionDef)) and "tax" in n.name.lower()), key=lambda n:n.lineno):
    print(f"{n.lineno}:{n.name}")
PY
rg -n "_handle_api_tax|def _tax_offset_routes|def _resolve_tax_offset|def rebuild_tax_offset|def _invalidate_tax_offset|def _schedule_tax_offset|def _tax_offset_|TaxApiRoutes|tax_certified|tax_offset" backend/src/fin_ops_platform/app/server.py
```

## Remaining Tax `Application` Surface

| Surface | Classification | Evidence |
| --- | --- | --- |
| `_configure_tax_offset_application_services(...)`, `_ensure_tax_offset_application_services(...)`, `_tax_offset_routes(...)`, `_tax_offset_runtime(...)`, `_tax_offset_query(...)` | dependency assembly / route-owner factory | These wire `TaxApiRoutes`, query/runtime services, certified import services and executors through explicit constructor ports. They do not own tax HTTP mapping after Rows 372-373. |
| `_resolve_tax_offset_read_session(...)`, `_resolve_tax_offset_mutation_session(...)`, `_tax_offset_actor_id(...)` | platform auth/session/actor ports | These are HTTP adapter ports injected into `TaxApiRoutes` for permission/session mapping and actor id derivation. They do not own tax business state transitions. |
| `_load_json_body(...)`, `_load_multipart_body(...)`, `_enqueue_import_process_job(...)`, `_serialize_import_job(...)`, `_import_job_processing_enabled(...)`, `_process_tax_certified_import_confirm_job(...)` | shared import/job adapter ports | Certified import preview/confirm HTTP mapping is route-owned; these remaining methods are shared body/job/worker adapters also used by other import flows. |
| `_get_or_build_tax_offset_month_payload(...)`, `_get_tax_offset_month_from_sql_read_model(...)`, `_get_tax_offset_month_summary_payload(...)`, `_tax_offset_summary_payload(...)`, `_tax_offset_expected_source_versions(...)`, `_tax_offset_source_versions(...)`, `_tax_offset_*_source_version(...)`, `_tax_offset_*_redis_cache_key(...)`, `_tax_offset_redis_ttl_seconds(...)`, `_empty_tax_offset_month_payload(...)`, `_tax_offset_month_entry_count(...)` | query/runtime/source-version/cache provider ports | These delegate to `TaxOffsetQueryService` or `TaxOffsetRuntimeService` and are retained for runtime, worker and compatibility seams. They no longer perform HTTP route ownership. |
| `_enqueue_tax_offset_read_model_refresh(...)`, `_invalidate_tax_offset_read_models(...)`, `_invalidate_tax_offset_read_model_scopes(...)`, `_enqueue_tax_offset_refresh_for_months(...)`, `_delete_tax_offset_redis_cache(...)`, `_tax_offset_read_model_scope_key(...)`, `_schedule_tax_offset_cache_warmup(...)` | gateway-backed refresh/cache ports | These route refresh or cache warmup through `TaxOffsetRuntimeService`, `ReadModelRefreshGateway` and `TaxOffsetCacheWarmupExecutor`. They do not direct-write durable queue rows from business service code. |
| `rebuild_tax_offset_read_model_scope(...)`, `_tax_offset_derived_lifecycle_executor(...)` | worker/derived lifecycle delegate ports | Prior slices moved rebuild behavior to `TaxOffsetWorkerRebuildExecutor` and derived lifecycle behavior to `TaxOffsetDerivedLifecycleExecutor`; `Application` remains the compatibility entry and dependency assembler. |
| `_tax_offset_scope_keys_for_import_preview(...)`, `_tax_offset_scope_keys_for_import_file_session(...)`, `_tax_offset_scope_keys_for_import_rows(...)` | import scope adapter ports | Thin scope extraction adapters used to translate import rows into read model refresh scopes. They are not HTTP route callbacks or projection writers. |
| `_persist_tax_offset_read_models_best_effort(...)` | explicit tax read-model persistence port | Explicit persistence remains available for runtime/executor paths after broad full-state snapshot persistence was quarantined in the earlier tax read-model slice. |

## Findings

- No `_handle_api_tax*` callback remains in `server.py`.
- `TaxApiRoutes.route(...)` now owns month, summary, calculate, plan save, certified import job polling, certified imports list, certified import preview and certified import confirm HTTP mapping.
- `server.py` no longer imports the certified import upload DTO or owns certified import preview/confirm response mapping.
- Remaining tax methods in `Application` are explicit dependency, platform, runtime, query, refresh, worker, cache, source-version, scope-adapter or compatibility delegate ports.
- The local `server.py` route-owner support for tax is accounted for, but tax full module closure is not claimed because production PostgreSQL/worker/App Status/high-row/browser/admin/write evidence remains final-validation scope.

## Decision

Tax route-owner local support is accounted for after:

- Row371 route owner audit;
- Row372 read/plan/import-job/list route callback collapse;
- Row373 certified import preview/confirm route callback collapse;
- prior tax read-model repository, freshness, worker rebuild, derived lifecycle, cache warmup and full-state snapshot quarantine slices;
- static guards preventing route callback regression.

The next local-first boundary should move to cost statistics route ownership, because `CostStatisticsApiRoutes` exists but `server.py` still owns direct `/api/cost-statistics*` dispatch branches and thin `_handle_api_cost_statistics*` callbacks.

## Next Boundary

`server-py:cost-statistics-route-owner-audit`

## Stop Gates For Next Boundary

- Do not change cost statistics behavior during the audit.
- Do not weaken `active/all` project scope grammar, read-model freshness/fail-closed behavior, export limits, or transaction/project detail error contracts.
- Do not claim cost statistics module/global closure from route-owner accounting alone.
- Do not run production validation or mutation while local implementation gaps remain.
