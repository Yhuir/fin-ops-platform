# Next Prompt

Continue after `server-py:workbench-refresh-status-payload-normalizer-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-refresh-status-payload-normalizer-extraction`.
- Row415 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-refresh-status-payload-normalizer-extraction-2026-06-25.md`.
- `WorkbenchRefreshStatusPayloadNormalizer` now owns refresh-status payload normalization and status-to-SSE-event mapping.
- Repository status lookup and legacy `/api/workbench` SQL fallback/payload handling remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-refresh-status-payload-normalizer-extraction` is complete:

- added `WorkbenchRefreshStatusPayloadNormalizer`;
- moved refresh-status payload normalization and event-name mapping out of `Application`;
- wired `WorkbenchQueryFacade` and `WorkbenchEventsApiRoutes` through the normalizer owner;
- preserved refresh-status API and SSE behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-read-route-owner-post-normalizer-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-refresh-status-payload-normalizer-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` Workbench refresh-status/SSE tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - repository status lookup in `_workbench_refresh_status_payload_for_scope(...)`;
   - legacy `/api/workbench` SQL fallback and payload builder path.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
