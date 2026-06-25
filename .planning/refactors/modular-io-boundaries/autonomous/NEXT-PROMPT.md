# Next Prompt

Continue after `server-py:workbench-api-payload-assembler-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-api-payload-assembler-extraction`.
- Row421 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-api-payload-assembler-extraction-2026-06-25.md`.
- `WorkbenchApiPayloadAssembler` now owns grouped payload post-processing orchestration for legacy Workbench API payloads.
- Raw payload builder, OA retention internals and tag derivation internals remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-api-payload-assembler-extraction` is complete:

- added `WorkbenchApiPayloadAssembler`;
- moved grouped payload post-processing orchestration out of `_build_api_workbench_payload(...)`;
- kept raw payload builder and helper side effects unchanged;
- preserved legacy grouped payload behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-raw-payload-builder-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-api-payload-assembler-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` and `tests/test_workbench_v2_api.py` raw payload, OA retention and relation repair tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_build_raw_workbench_payload(...)`.
   - live/OA payload merge helpers;
   - auto-pair sync and OA attachment relation repair helpers;
   - pair relation application and override application.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
