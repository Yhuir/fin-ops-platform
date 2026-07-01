# server-py:workbench-row-detail-route-owner-extraction

**Date:** 2026-06-24
**Status:** implementation-closed
**Previous boundary:** `server-py:workbench-row-detail-route-owner-audit`
**Next boundary:** `server-py:workbench-group-detail-route-owner-audit`

## Goal

Extract Workbench row detail payload/fallback orchestration from `Application` behind an explicit read-only route owner while preserving `GET /api/workbench/rows/{row_id}` response shape, fallback order, override behavior and production PostgreSQL fail-closed behavior.

This is a narrow server ownership implementation slice. It does not change Workbench row detail business semantics, Workbench groups, refresh status, settings, active generation publishing, matching workers, read model queue behavior, legacy `/workbench/actions/*`, modern Workbench action behavior, frontend behavior, production state, or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-row-detail-route-owner-audit.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_workbench_query_facade.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Change Summary

- Added `WorkbenchRowDetailApiRoutes` in `routes_workbench.py`.
- Moved row detail fallback orchestration into `WorkbenchRowDetailApiRoutes.get_payload(...)`.
- Preserved fallback order:
  1. ETC summary row detail.
  2. live Workbench row detail.
  3. cached read model rows.
  4. `WorkbenchQueryFacade.row_detail(...)`.
  5. opaque OA row id fail-closed behavior when no month hint exists.
  6. allowed legacy `WorkbenchApiRoutes.get_row_detail(...)` fallback.
  7. row override application.
- `Application._get_api_workbench_row_detail_payload(...)` is now a thin delegate to `_workbench_row_detail_routes().get_payload(...)`.
- Removed app-owned `_workbench_row_detail_from_query_facade(...)` and `_workbench_row_detail_route_fallback_allowed(...)`.
- `Application` now only assembles explicit dependencies for `WorkbenchRowDetailApiRoutes` and keeps HTTP `404`/`200` response mapping in `_handle_api_workbench_row_detail(...)`.

## Preserved Contract

- `GET /api/workbench/rows/{row_id}` still returns `404 {"error": "workbench_row_not_found", "row_id": ...}` on `KeyError`.
- Live row detail still wins over cache/query/legacy fallback.
- Cached read model rows still apply only when fresh enough for `_resolve_rows_from_cached_read_models(...)`.
- Opaque OA row ids still use `WorkbenchQueryFacade.row_detail(...)` after live/cache miss and do not fall through to legacy route detail in production PostgreSQL runtime.
- Production PostgreSQL runtime now blocks the legacy route fallback completely; old route query service in-memory records do not re-enable it.
- Row overrides are still applied exactly once before returning the row payload.
- The new route owner is read-only; it does not import relation command services, enqueue read model refresh, write dirty scopes/outbox/readiness, or mutate canonical facts.

## Next Boundary

The next bounded server ownership slice should be:

`server-py:workbench-group-detail-route-owner-audit`

Rationale:

- `GET /api/workbench/groups/detail` is the adjacent Workbench detail read surface.
- `docs/modules/reconciliation-workbench/README.md` requires group detail to verify active generation `source_versions`, `read_model_status` and `read_model_version`, and not return stale group detail as fresh.
- Current group detail HTTP parameter validation and facade delegation still live in `Application._handle_api_workbench_group_detail(...)`.
- Auditing group detail next keeps the shared server ownership work on one narrow read route at a time.

## Non-Goals

- Do not change Workbench group detail behavior in this slice.
- Do not remove `WorkbenchApiRoutes.get_row_detail(...)` from non-SQL/legacy compatibility mode in this slice; production SQL read model runtime must not call it.
- Do not mark Workbench relation, read model, worker, server.py or Go admission globally closed.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rules, relation states, matching rules or amount logic changed.
2. Service-layer tests: not applicable; no service behavior changed. The new route owner uses explicit callables and preserves existing service dependencies.
3. API contract tests: covered by existing row detail API/runtime tests for success, not-found, production fallback blocking and opaque OA SQL fallback.
4. Read model/cache/background job tests: covered by existing row detail tests for cached stale rejection and SQL active generation fallback; no worker behavior changed.
5. Frontend component and interaction tests: not applicable; row detail API shape and frontend drawer behavior did not change.
6. End-to-end business-flow tests: not required for this route-owner extraction; no cross-module behavior changed.
7. Existing feature regression tests: covered by existing row detail tests plus static boundary guard added for row detail route owner extraction.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_row_detail_route_owner_extraction_updates_queue tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_row_detail_route_owner_audit_selects_extraction tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_row_detail_prefers_live_service_and_applies_override_without_fallback tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_row_detail_route_fallback_applies_override_after_live_and_cache_miss tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_row_detail_production_sql_runtime_blocks_route_fallback_after_live_and_cache_miss tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_row_detail_production_sql_runtime_ignores_stale_cached_read_model_row tests.test_workbench_sql_runtime.WorkbenchSqlRuntimeTests.test_row_detail_sql_runtime_uses_query_facade_for_opaque_oa_after_live_and_cache_miss tests.test_workbench_query_facade.WorkbenchQueryFacadeTests.test_row_detail_reads_sql_row_without_application_live_sync -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- Row 215 moves from `pending` to `implementation-closed`.
- Row 216 is added as the next pending boundary: `server-py:workbench-group-detail-route-owner-audit`.
- Module closure remains `implementation-gap-open`; this closes only the row detail route-owner extraction slice.
