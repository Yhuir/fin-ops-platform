# Next Prompt

Continue after `server-py:workbench-group-row-payload-helper-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-group-row-payload-helper-extraction`.
- Row449 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-group-row-payload-helper-extraction-2026-06-25.md`.
- `WorkbenchGroupRowPayloadHelper` now owns paired/open extraction, ignored-row filtering, grouping service invocation and OA status carry-over.
- Cache/read payload helper extraction remains deferred to a dedicated slice.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-group-row-payload-helper-extraction` is complete:

- added `WorkbenchGroupRowPayloadHelper`;
- moved paired/open extraction, ignored-row filtering, grouping service invocation and OA status carry-over out of `Application._group_row_payload(...)`;
- preserved existing `Application` helper name as delegate;
- preserved grouping behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-cache-read-payload-helper-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-group-row-payload-helper-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` and `tests/test_workbench_v2_api.py` raw payload, OA retention and relation repair tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_can_use_cached_workbench_payload(...)`;
   - `_can_persist_workbench_payload(...)`;
   - `_can_fallback_to_stale_workbench_payload(...)`;
   - `_oa_status_is_ready_for_cache(...)`.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
