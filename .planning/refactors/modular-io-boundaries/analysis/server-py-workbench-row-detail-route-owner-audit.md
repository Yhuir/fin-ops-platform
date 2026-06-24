# server-py:workbench-row-detail-route-owner-audit

**Date:** 2026-06-24
**Status:** analysis-closed
**Previous boundary:** `server-py:modern-workbench-action-route-owner-local-closure-audit`
**Next boundary:** `server-py:workbench-row-detail-route-owner-extraction`

## Goal

Audit `GET /api/workbench/rows/{row_id}` route ownership after modern Workbench action route-owner local closure, verify the current live/cache/SQL fallback contract and no-write boundary, then select the next bounded server ownership slice.

This is an audit slice. It does not change row detail runtime behavior, response shape, fallback order, freshness semantics, frontend drawer behavior, Workbench action behavior, relation writes, read model refresh behavior, production state, or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-local-closure-audit.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/reconciliation-workbench/implementation-notes.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_workbench_query_facade.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `WorkbenchApiRoutes`, row detail route ownership and Workbench query facade entry points.

## Findings

`GET /api/workbench/rows/{row_id}` is still owned by `Application` for payload assembly and fallback orchestration:

- `Application._handle_api_workbench_row_detail(...)` maps `KeyError` to `404 {"error": "workbench_row_not_found", "row_id": ...}` and serializes successful payloads.
- `Application._get_api_workbench_row_detail_payload(...)` owns the row detail fallback chain:
  1. ETC invoice summary row detail.
  2. `LiveWorkbenchService.get_row_detail(...)`.
  3. cached read model row resolution through `_resolve_rows_from_cached_read_models(...)`.
  4. SQL active generation lookup through `WorkbenchQueryFacade.row_detail(...)`.
  5. opaque OA row id fail-closed path when no month can be inferred.
  6. legacy `WorkbenchApiRoutes.get_row_detail(...)` fallback only when `_workbench_row_detail_route_fallback_allowed(...)` allows it.
  7. row override application through `WorkbenchOverrideService.apply_to_row(...)`.
- `Application._workbench_row_detail_from_query_facade(...)` adapts `WorkbenchQueryFacade.row_detail(...)` into a row-only payload.
- `Application._workbench_row_detail_route_fallback_allowed(...)` blocks the old route fallback in production PostgreSQL runtime unless the route query service still has an in-memory row record.

The current no-write boundary is locally protected:

- `docs/modules/reconciliation-workbench/README.md` states that `GET /api/workbench/rows/{row_id}` is a read interface and must not write relation state or use `WorkbenchRelationCommandService`.
- `WorkbenchQueryFacade.row_detail(...)` reads `get_workbench_row_detail(...)` from the SQL repository and returns read model status payloads; it does not enqueue writes or call relation command services.
- `PostgresReadModelRepository.get_workbench_row_detail(...)` reads active generation rows and source versions; it does not write canonical facts, dirty scopes, outbox, readiness or relation state.
- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests::test_row_detail_reads_sql_row_without_application_live_sync` verifies SQL row detail can be read without application live sync.
- `tests/test_workbench_sql_runtime.py` covers live path, route fallback, production PostgreSQL fallback blocking, stale cached row rejection and opaque OA row SQL active generation fallback.

## Remaining Gap

The route contract is locally tested, but ownership is still mixed in `Application`:

- The fallback orchestration, SQL query facade adaptation, production fallback policy and override application are not behind an explicit row-detail route owner.
- `WorkbenchApiRoutes.get_row_detail(...)` remains an old route fallback surface and does not own the full production row detail contract.
- Keeping this logic in `Application` slows server.py residual closure and makes future row detail/read model freshness changes easier to misplace.

## Next Boundary

The next bounded implementation slice should be:

`server-py:workbench-row-detail-route-owner-extraction`

Rationale:

- The route is read-only and has focused tests covering fallback order and production fail-closed behavior.
- The extraction can be limited to a new explicit route owner for row detail payload assembly and fallback orchestration while preserving `Application` as HTTP status/response serializer.
- The extraction should keep `Application` responsible only for route dispatch and JSON response mapping, not live/cache/SQL/legacy fallback decisions.
- This is narrower and safer than extracting Workbench groups, refresh status, settings, active generation or matching worker surfaces.

## Non-Goals

- Do not change row detail response shape, status codes, fallback order, stale/fresh semantics, override behavior, frontend detail drawer behavior or existing tests.
- Do not change Workbench groups, refresh status, events, settings, active generation publishing, matching worker, read model queue, relation writes, legacy `/workbench/actions/*` or modern Workbench action behavior.
- Do not remove `WorkbenchApiRoutes.get_row_detail(...)` yet; classify it during the extraction and keep/delete only with caller evidence.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rules, matching rules or relation states changed.
2. Service-layer tests: not applicable for this audit; next extraction should preserve existing service/fallback behavior.
3. API contract tests: existing Workbench SQL runtime row detail tests cover response/status/fallback behavior; no API changed in this audit.
4. Read model/cache/background job tests: existing row detail tests cover live/cache/SQL active generation fallback and stale cached row rejection; no read model code changed in this audit.
5. Frontend component and interaction tests: not applicable; no frontend behavior changed.
6. End-to-end business-flow tests: not required for this audit; no runtime behavior changed.
7. Existing feature regression tests: applicable through static state-machine guard and existing row detail regression tests.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_row_detail_route_owner_audit_selects_extraction tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_modern_workbench_action_route_owner_local_closure_audit_selects_row_detail_audit tests.test_workbench_query_facade.WorkbenchQueryFacadeTests.test_row_detail_reads_sql_row_without_application_live_sync tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_row_detail_sql_runtime_uses_query_facade_for_opaque_oa_after_live_and_cache_miss -v
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- Row 214 moves from `pending` to `analysis-closed`.
- Row 215 is added as the next pending boundary: `server-py:workbench-row-detail-route-owner-extraction`.
- Module closure remains `implementation-gap-open`; this audit only selects the next Workbench row detail route-owner implementation slice.
