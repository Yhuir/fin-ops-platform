# server-py:cost-statistics-route-owner-audit

Status: `analysis-closed`

Date: 2026-06-25

## Boundary

Audit remaining `/api/cost-statistics*` route ownership in `Application` and select the next bounded local implementation slice.

This is a local `server.py` route-owner audit. It does not claim cost statistics module closure, global modular IO closure, or production PostgreSQL/worker/browser evidence closure.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_cost_statistics.py`
- `tests/test_cost_statistics_api.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/state-machine.md`
- `docs/modules/cost-statistics/tests.md`
- prior cost statistics read-model implementation notes and analysis files

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
rg -n "CostStatisticsApiRoutes|_handle_api_cost_statistics|def _cost_statistics_routes|/api/cost-statistics" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_cost_statistics.py tests/test_platform_runtime_boundary_guards.py tests/test_cost_statistics_api.py
```

## Current Route Ownership

`CostStatisticsApiRoutes` already owns response mapping for:

- month summary;
- explorer;
- project detail;
- export;
- export preview;
- transaction detail;
- invalid project scope errors;
- export row-limit and not-found error responses;
- XLSX file response delegation through an injected `file_response` port.

`Application` still owns direct dispatch branches for:

- `GET /api/cost-statistics`;
- `GET /api/cost-statistics/explorer`;
- `GET /api/cost-statistics/export-preview`;
- `GET /api/cost-statistics/export`;
- `GET /api/cost-statistics/projects/{project_name}`;
- `GET /api/cost-statistics/transactions/{transaction_id}`.

`Application` also still owns thin callbacks:

- `_handle_api_cost_statistics(...)`;
- `_handle_api_cost_statistics_explorer(...)`;
- `_handle_api_cost_statistics_project(...)`;
- `_handle_api_cost_statistics_export(...)`;
- `_handle_api_cost_statistics_export_preview(...)`;
- `_handle_api_cost_statistics_transaction(...)`.

## Findings

- The six `_handle_api_cost_statistics*` callbacks are thin delegates to `CostStatisticsApiRoutes`.
- The heavy cost statistics behavior is already outside `Application`:
  - query/read-model/freshness behavior in `CostStatisticsQueryService` and `CostStatisticsRuntimeService`;
  - business/export/detail behavior in `CostStatisticsService`;
  - derived lifecycle behavior in `CostStatisticsDerivedLifecycleExecutor`;
  - full-state read model snapshot write path already quarantined.
- The direct `Application.handle_request(...)` branches still parse query params and route path fragments before calling the thin callbacks.
- This is safe to collapse into a `CostStatisticsApiRoutes.route(...)` method with explicit query parser and optional bool parser ports.
- The next slice should not touch cost attribution, `active/all` scope grammar, read-model freshness, export row limits, XLSX generation, cache keys, worker fan-out or production behavior.

## Decision

Select `server-py:cost-statistics-route-callback-collapse` as the next bounded local implementation slice.

Expected implementation shape:

- add `CostStatisticsApiRoutes.route(method, route_path, query)` or equivalent route-owner dispatch;
- inject any needed parser ports from `Application`, especially optional boolean parsing for export options;
- delegate `/api/cost-statistics*` branches from `Application` to the route owner;
- remove the now-redundant `_handle_api_cost_statistics*` callbacks from `server.py`;
- add/update static Guard coverage so cost statistics route callbacks cannot move back into `Application`;
- run targeted cost statistics API and route-owner Guard tests.

## Stop Gates For Next Boundary

- Do not change payload shape, status codes, filenames, export limit errors or invalid project scope errors.
- Do not weaken `active/all` project scope grammar.
- Do not change read-model freshness/fail-closed, parent aggregate, cache or worker behavior.
- Do not run production validation or mutation.
