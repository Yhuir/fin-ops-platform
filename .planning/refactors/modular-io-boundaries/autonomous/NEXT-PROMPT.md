# Next Prompt

Continue after `server-py:workbench-raw-payload-row-id-set-helper-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-raw-payload-row-id-set-helper-extraction`.
- Row463 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-raw-payload-row-id-set-helper-extraction-2026-06-25.md`.
- `WorkbenchOaAttachmentContextRowIndex` now owns generic raw payload row-id set extraction as well as OA attachment context row indexing.
- Relation display/pair metadata helpers remain deferred to a dedicated slice.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-raw-payload-row-id-set-helper-extraction` is complete:

- added `WorkbenchOaAttachmentContextRowIndex.raw_payload_row_ids(...)`;
- moved `_raw_workbench_payload_row_ids(...)` logic out of `Application`;
- preserved existing `Application` helper name as a delegate;
- extended static Guard and local tests;
- avoided production validation.

## Next Boundary

`server-py:workbench-pair-relation-display-payload-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-raw-payload-row-id-set-helper-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/server.py` around `_apply_pair_relation_to_row(...)` and `_pair_relation_display_payload(...)`
   - relevant pair metadata and display-policy tests/guards
3. Audit pair relation display/payload helpers:
   - relation field and display payload mapping;
   - mode-specific decorators;
   - amount check propagation;
   - available actions;
   - metadata/tag side effects.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from this row-id helper extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move unrelated grouping, relation repair or route logic in this slice.
