# Next Prompt

Continue after `server-py:workbench-selected-scope-raw-oa-payload-builder-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-selected-scope-raw-oa-payload-builder-extraction`.
- Row433 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-selected-scope-raw-oa-payload-builder-extraction-2026-06-25.md`.
- `WorkbenchSelectedScopeRawOaPayloadBuilder` now owns selected month/retained row filtering, row serialization, section assignment and summary construction.
- Retention date parsing and canonical OA attachment invoice append/replace/dedupe/summary repair remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-selected-scope-raw-oa-payload-builder-extraction` is complete:

- added `WorkbenchSelectedScopeRawOaPayloadBuilder`;
- moved selected month/retained row filtering, row serialization, section assignment and summary construction out of `_raw_oa_payload_for_selected_scope(...)`;
- kept manual retained row ids, record snapshots, serialization and OA status as explicit ports;
- preserved selected-scope raw OA payload behavior with local tests and existing v2 API regression coverage;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-retention-date-parser-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-selected-scope-raw-oa-payload-builder-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` and `tests/test_workbench_v2_api.py` raw payload, OA retention and relation repair tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_parse_oa_retention_date(...)`;
   - app settings input contract;
   - invalid cutoff behavior;
   - retained-all callers.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
