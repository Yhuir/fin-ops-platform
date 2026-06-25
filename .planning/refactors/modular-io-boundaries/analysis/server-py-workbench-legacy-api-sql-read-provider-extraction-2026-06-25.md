# server-py:workbench-legacy-api-sql-read-provider-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:workbench-legacy-api-sql-fallback-audit`
**Next boundary:** `server-py:workbench-legacy-api-payload-builder-audit`

## Purpose

Move legacy `/api/workbench` SQL fallback read-model view handling out of `Application` into an explicit provider while preserving the existing SQL-first API contract.

## Implementation

- Added `WorkbenchLegacyApiSqlReadProvider` and `WorkbenchLegacyApiSqlReadResult` in `backend/src/fin_ops_platform/services/workbench_legacy_api_sql_read_provider.py`.
- The provider owns:
  - `get_workbench_view(...)` repository lookup;
  - SQL miss response payload and `api_miss` refresh enqueue;
  - stale source-version response payload and `api_stale` refresh enqueue;
  - OA projection sync refresh enqueue and metadata payload mapping;
  - `generated_at` and `rows_page` response passthrough.
- `Application._handle_api_workbench(...)` now delegates SQL read-model handling to the provider and only maps the result to `_json_response(...)`.
- Removed `Application._handle_api_workbench_from_sql_read_model(...)`.

## Inputs

- Month and optional pagination/filter/search query values.
- Workbench SQL read repository provider.
- Scope key, freshness, Workbench refresh enqueue and OA sync enqueue ports.
- Current OA parser/projection version providers.

## Outputs

- Optional `WorkbenchLegacyApiSqlReadResult` for the SQL branch.
- `None` when no SQL view repository port exists, preserving legacy builder fallback/non-production behavior.

## State And Events

The provider is read-only except for explicit refresh enqueue ports already owned by the previous app helper. It does not construct HTTP responses, parse auth, write read-model tables, clear caches, persist state, or own the raw payload builder.

## Read Model/Freshness Contract

The SQL-first contract is unchanged:

- missing SQL view returns `202 Accepted` refreshing and enqueues `api_miss`;
- stale source versions return `200 OK` stale and enqueue `api_stale`;
- OA parser/projection stale view returns `202 Accepted` refreshing and enqueues OA sync;
- fresh SQL view returns `200 OK` with backend-only fields and rows-page passthrough;
- absent SQL repository still lets `_handle_api_workbench(...)` decide between production fail-closed and local legacy builder fallback.

## Tests And Guards

- Added `tests/test_workbench_legacy_api_sql_read_provider.py`.
- Preserved existing `/api/workbench` SQL runtime tests for SQL hit, miss, stale/refreshing, production fail-closed and query argument passthrough.
- Added static Guard coverage proving `Application` no longer owns `_handle_api_workbench_from_sql_read_model(...)` and the provider has no HTTP response/write/runtime side-effect dependencies.

## Out Of Scope

- The raw payload builder remains in `Application`.
- Legacy grouped payload decoration/tag derivation remains unchanged.
- No production browser/admin/write validation was run.

## Completion Semantics

This row may be marked `local-implementation-closed` after local tests, static Guard, docs verification and diff checks pass. It does not claim Workbench module/global closure.
