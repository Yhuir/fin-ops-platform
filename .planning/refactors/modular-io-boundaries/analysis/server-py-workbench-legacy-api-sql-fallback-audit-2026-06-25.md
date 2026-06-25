# server-py:workbench-legacy-api-sql-fallback-audit

**Date:** 2026-06-25
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-refresh-status-payload-provider-extraction`
**Selected next boundary:** `server-py:workbench-legacy-api-sql-read-provider-extraction`

## Purpose

Audit legacy `/api/workbench` SQL fallback and payload builder surfaces in `server.py`.

## Findings

- `_handle_api_workbench(...)` still owns top-level legacy `/api/workbench` dispatch between SQL read model, production fail-closed behavior and legacy builder fallback.
- `_handle_api_workbench_from_sql_read_model(...)` owns SQL read-model view lookup, miss/stale refresh enqueue, OA projection sync refresh enqueue, read model metadata mapping and rows-page passthrough.
- `_build_api_workbench_payload(...)` and `_build_raw_workbench_payload(...)` remain large legacy grouped/raw payload builders with live OA/local state side effects.
- Existing tests cover SQL hit without legacy build, SQL miss enqueue, production no-SQL fail-closed, OA parser/projection sync stale handling, backend-only field preservation and page/filter argument passthrough.

## Decision

Select `server-py:workbench-legacy-api-sql-read-provider-extraction` as the next narrow local implementation boundary.

This extracts only the SQL read-model view-to-payload branch. It does not move the raw payload builder because that path is broader and has many downstream local state and OA attachment side effects.

## Out Of Scope

- No production browser/admin/write validation.
- No raw payload builder migration.
- No grouped payload/tag decoration migration.
- No Go/Fiber/worker implementation.

## Completion Semantics

This row may be marked `analysis-closed`. It selects a local implementation boundary and does not claim Workbench module/global closure.
