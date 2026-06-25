# Next Prompt

Continue after `server-py:workbench-retained-all-oa-payload-builder-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-retained-all-oa-payload-builder-extraction`.
- Row429 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-retained-all-oa-payload-builder-extraction-2026-06-25.md`.
- `WorkbenchRetainedAllOaPayloadBuilder` now owns retained all-OA payload orchestration.
- Supplemental retained OA row selection and selected-scope raw OA payload internals remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-retained-all-oa-payload-builder-extraction` is complete:

- added `WorkbenchRetainedAllOaPayloadBuilder`;
- moved no-cutoff all-scope load/promotion, retained/supplemental sync orchestration, parse suppression and selected-scope call orchestration out of `_build_retained_all_oa_row_payload(...)`;
- kept supplemental retained OA row selection and selected-scope raw OA payload construction as compatibility ports;
- preserved retained all-OA behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-supplemental-retained-oa-row-selection-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-retained-all-oa-payload-builder-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` and `tests/test_workbench_v2_api.py` raw payload, OA retention and relation repair tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_supplemental_retained_oa_row_ids(...)`;
   - retained OA supplemental relation read port;
   - live row resolution;
   - retention date checks.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
