# Next Prompt

Continue after `server-py:workbench-cache-read-payload-helper-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-cache-read-payload-helper-extraction`.
- Row451 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-cache-read-payload-helper-extraction-2026-06-25.md`.
- `WorkbenchCacheReadPayloadHelper` now owns cached payload use/persist/fallback gates, OA status readiness and schema/hash/parser/rules summary checks.
- OA invoice offset rebuild helper extraction remains deferred to a dedicated slice.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-cache-read-payload-helper-extraction` is complete:

- added `WorkbenchCacheReadPayloadHelper`;
- moved cached payload use/persist/fallback gates, OA status readiness and schema/hash/parser/rules summary checks out of `Application`;
- preserved existing `Application` helper names as delegates;
- preserved cache readiness behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-oa-invoice-offset-rebuild-helper-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-cache-read-payload-helper-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` and `tests/test_workbench_v2_api.py` raw payload, OA retention and relation repair tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_cached_payload_needs_oa_invoice_offset_rebuild(...)`;
   - OA invoice offset applicant settings;
   - attachment invoice row checks;
   - cost exclusion tag requirements.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
