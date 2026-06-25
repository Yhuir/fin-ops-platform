# Next Prompt

Continue after `server-py:workbench-oa-attachment-context-row-index-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-oa-attachment-context-row-index-extraction`.
- Row461 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-attachment-context-row-index-extraction-2026-06-25.md`.
- `WorkbenchOaAttachmentContextRowIndex` now owns raw payload row indexing, attachment context detection and OA id fallback matching.
- Generic raw row-id set extraction remains deferred to a dedicated slice.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-oa-attachment-context-row-index-extraction` is complete:

- added `WorkbenchOaAttachmentContextRowIndex`;
- moved raw payload row indexing and OA attachment context matching out of `Application`;
- preserved existing `Application` helper names as delegates;
- preserved direct derived OA id, parent id, source matcher and invoice id fallback behavior;
- added static Guard and local tests;
- avoided production validation.

## Next Boundary

`server-py:workbench-raw-payload-row-id-set-helper-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-attachment-context-row-index-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/server.py` around `_raw_workbench_payload_row_ids(...)`
   - relevant static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit generic raw payload row-id set extraction:
   - paired/open section handling;
   - OA/bank/invoice pane handling;
   - row id normalization;
   - current callers and whether existing row-index service should own it.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from this row-index extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move unrelated grouping, relation display or row tag logic in this slice.
