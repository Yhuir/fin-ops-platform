# server-py:workbench-group-detail-route-owner-audit

**Date:** 2026-06-24
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-row-detail-route-owner-extraction`
**Next boundary:** `server-py:workbench-group-detail-route-owner-extraction`

## Goal

Audit `GET /api/workbench/groups/detail` ownership before implementation. The target is to determine whether group detail HTTP validation and response mapping can move behind an explicit route owner without changing group detail response shape, status codes, freshness/stale behavior, source-version proof, read model refresh enqueue behavior, frontend group drawer behavior, active generation publishing or relation write behavior.

This is an analysis-only server ownership slice. It does not change runtime code and does not implement Go, Go Fiber or Go Worker.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-row-detail-route-owner-extraction.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/workbench_query_facade.py`
- `tests/test_workbench_query_facade.py`
- `tests/test_workbench_sql_runtime.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Current Ownership

`Application._handle_api_workbench_group_detail(...)` currently owns only HTTP-level concerns:

- Default `month` to `all`.
- Normalize `zone` and reject values outside `open` / `paired` with `400 invalid_workbench_zone`.
- Normalize `group_id` and reject empty values with `400 invalid_workbench_group_detail_request`.
- Delegate to `WorkbenchQueryFacade.group_detail(...)`.
- Convert `WorkbenchQueryResult.status_code` and payload into the Flask JSON response.

`Application._handle_api_workbench_group_detail(...)` does not write relation state, command services, dirty scopes, outbox events, readiness, active generation rows, Redis cache or App Status.

## Freshness And Read Model Boundary

`WorkbenchQueryFacade.group_detail(...)` is the freshness/status proof boundary for this route:

- It resolves the Workbench scope key from `month`.
- It requires a repository method named `get_workbench_group_detail(...)`.
- Missing repository support returns `503 read_model_unavailable`.
- Missing SQL migration errors return `503 read_model_unavailable`.
- Missing group data returns `404 workbench_group_not_found`.
- Returned group payloads are checked with `_stale_reasons(group.get("source_versions"), scope_key=group_scope_key)`.
- Stale source versions or non-fresh `read_model_status` do not return the old group as fresh; they enqueue a Workbench refresh and return `404 workbench_group_not_found` with `read_model_status` and stale reasons when available.
- Fresh groups return `200` with `month`, `scope_key`, `zone`, `group_id`, `group`, and `read_model_status: fresh`.

`PostgresReadModelRepository.get_workbench_group_detail(...)` is the SQL active generation reader. Existing tests prove it reads only the active generation and includes the active generation freshness contract: `source_versions`, `read_model_status` and `read_model_version`.

## Existing Test Evidence

- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests.test_group_detail_stale_source_versions_do_not_return_stale_group`
- `tests/test_workbench_query_facade.py::WorkbenchQueryFacadeTests.test_group_detail_refreshing_status_does_not_return_stale_group`
- `tests/test_workbench_sql_runtime.py::WorkbenchSqlRuntimeTests.test_repository_group_detail_includes_active_generation_freshness_contract`
- `docs/modules/reconciliation-workbench/tests.md` records the group detail freshness gate as covered.

These tests cover the read model freshness contract. They do not yet prove that HTTP validation and facade response mapping are owned by an explicit route owner instead of `Application`.

## Boundary Classification

- Route path: `GET /api/workbench/groups/detail`
- Current route owner: `Application._handle_api_workbench_group_detail(...)`
- Target route owner: a narrow Workbench group detail route owner in `routes_workbench.py`.
- Query/read model owner: `WorkbenchQueryFacade.group_detail(...)`
- SQL owner: `PostgresReadModelRepository.get_workbench_group_detail(...)`
- Canonical fact owner: unchanged; group detail must not write canonical facts.
- Event/refresh owner: unchanged; stale group detail refresh enqueue stays inside the existing query facade boundary.
- Permission/auth owner: unchanged; no new permission behavior is introduced in this slice.
- Legacy status: no legacy group-detail fallback was found in this audit.

## Remaining Gap

`Application._handle_api_workbench_group_detail(...)` still owns route-local validation and facade response mapping. This is small enough to extract safely as the next bounded implementation slice:

`server-py:workbench-group-detail-route-owner-extraction`

The extraction should preserve:

- `400 invalid_workbench_zone`
- `400 invalid_workbench_group_detail_request`
- `WorkbenchQueryFacade.group_detail(...)` delegation arguments
- returned status codes and payloads from `WorkbenchQueryResult`
- no-write route behavior
- existing freshness/source-version/read-model-status behavior inside the facade

## Non-Goals

- Do not change group detail response shape, status codes, freshness/stale behavior, source-version proof, read model refresh enqueue behavior or frontend group drawer behavior.
- Do not change Workbench row detail, groups page, refresh status, settings, active generation publishing, matching worker, read model queue, legacy `/workbench/actions/*`, relation write behavior or modern Workbench action behavior.
- Do not mark Workbench relation, read model, worker, server.py or Go admission globally closed.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no matching, relation, amount, status transition or business rule changed.
2. Service-layer tests: not applicable for this analysis-only slice; existing facade tests cover freshness/status behavior.
3. API contract tests: covered by existing group detail status/payload tests at facade and SQL repository boundaries; extraction slice should add/retain static route-owner coverage without changing API shape.
4. Read model/cache/background job tests: covered by existing stale source-version and refreshing-status facade tests; no worker behavior changed.
5. Frontend component and interaction tests: not applicable; frontend group drawer behavior and API shape are unchanged.
6. End-to-end business-flow integration tests: not required for this audit; no cross-module behavior changed.
7. Existing feature regression tests: covered by static queue/analysis guard plus existing group detail freshness tests.

## State Impact

- Row 216 moves from `pending` to `analysis-closed`.
- Row 217 is added as the next pending boundary: `server-py:workbench-group-detail-route-owner-extraction`.
- Module closure remains `implementation-gap-open`; this closes only the group detail route-owner audit slice.
