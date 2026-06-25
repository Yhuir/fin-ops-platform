# planning:post-no-oa-server-local-support-next-boundary-selection

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:no-oa-bank-batch-post-display-policy-local-closure-audit`
**Next boundary:** `server-py:workbench-groups-read-route-owner-extraction`

## Purpose

Select the next safe non-production local boundary after no-OA local `server.py` support was accounted. This selection keeps production browser/admin/write evidence deferred while residual local `server.py` modularization gaps remain.

## Evidence Read

- `autonomous/NEXT-PROMPT.md` required this row to choose the next local boundary from residual `server.py` route/support surfaces.
- `autonomous/MODULE-QUEUE.md` row 405 is `production-evidence-deferred`; row 406 was the first pending row.
- `backend/src/fin_ops_platform/app/routes_workbench.py` currently owns Workbench row detail and group detail route validation, but `WorkbenchApiRoutes` only exposes legacy `get_workbench`, row detail and action helpers.
- `backend/src/fin_ops_platform/app/server.py` still directly dispatches and handles:
  - `GET /api/workbench/summary`;
  - `GET /api/workbench/groups`;
  - `GET /api/workbench/refresh-status`;
  - `GET /api/workbench/events`.
- `server.py` group-list handling still owns `zone` validation, `detail_level` normalization, `search_mode` normalization, JSON query parameter parsing, facade invocation and HTTP error mapping.
- Existing tests already cover `WorkbenchGroupDetailApiRoutes` in `tests/test_workbench_routes.py`, giving a local pattern for a narrow route-owner extraction test without PostgreSQL.
- `docs/modules/reconciliation-workbench/README.md` and `tests.md` identify Workbench group reads as high-fanout read-model/freshness surfaces, so the slice must preserve facade-owned freshness/source-version behavior and avoid changing active generation semantics.

## Boundary Decision

Select `server-py:workbench-groups-read-route-owner-extraction` as the next executable local implementation boundary.

The first implementation slice should move the read-only Workbench `summary` and `groups` HTTP validation/mapping into `routes_workbench.py`, behind explicit facade and normalizer ports. `Application` should remain responsible for top-level dispatch, JSON `Response` construction, metrics and dependency assembly.

## Inputs

- HTTP method/path/query for:
  - `GET /api/workbench/summary`;
  - `GET /api/workbench/groups`.
- Existing `WorkbenchQueryFacade` provider from `Application._workbench_query_facade`.
- Existing group query normalizers:
  - `normalize_workbench_group_detail_level`;
  - `normalize_workbench_group_search_mode`;
  - `stable_json_value`.

## Outputs

- `(HTTPStatus, payload)` route-owner results for summary and groups.
- Unchanged `Application` JSON response mapping and Workbench API metrics.
- Local route-owner tests proving normalized delegation and invalid query rejection.
- Static guard coverage preventing group-list validation from returning to `Application`.

## State And Events

- No write-side state changes.
- No canonical relation, dirty-scope, outbox, readiness, cache or App Status mutation.
- Read model freshness/source-version behavior remains owned by `WorkbenchQueryFacade`; the route owner only validates query input and delegates.

## Permissions

No new permission rule is introduced. The existing top-level `Application.handle_request(...)` auth/session path remains unchanged.

## Read Model/Freshness Impact

The slice must not alter Workbench SQL active generation, read model freshness, source-version proof, `refresh_status`, Redis cache behavior or operation barrier semantics. Those remain inside `WorkbenchQueryFacade` and existing read model services.

## Tests

Targeted local tests:

- Extend `tests/test_workbench_routes.py` for summary and groups route-owner behavior.
- Run the focused Workbench route tests.
- Run `tests/test_platform_runtime_boundary_guards.py` focused guard if updated.
- Run `bash scripts/verify.sh docs`, `git diff --check` and `git diff --cached --check` before commit.

PostgreSQL, production browser, admin and controlled write evidence are not required for this local route-owner slice.

## Docs Impact

This is an internal route-owner refactor for an existing Workbench API contract. Module docs do not need long-term behavior updates unless the implementation changes API shape, freshness fields, permissions or user-visible behavior. The analysis/state files carry the refactor evidence.

## Out Of Scope

- Do not move `GET /api/workbench/events` in the same slice; its SSE registry and heartbeat lifecycle need a dedicated boundary.
- Do not move `GET /api/workbench/refresh-status` unless it remains trivial after group read extraction; prefer a follow-up route-owner slice if needed.
- Do not touch relation writes, preview/apply flows, active generation publish logic, matching worker logic, production browser runner, admin auth seam or controlled write runbook.

## Completion Semantics

Row 406 is analysis-only and closes as `analysis-closed`. Row 407 is added as the next local implementation row. No production validation or module/global closure is claimed.
