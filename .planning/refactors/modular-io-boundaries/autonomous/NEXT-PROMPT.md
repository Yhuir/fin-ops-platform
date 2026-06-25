# Next Prompt

Continue after `server-py:workbench-canonical-oa-attachment-raw-payload-repairer-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-canonical-oa-attachment-raw-payload-repairer-extraction`.
- Row437 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-canonical-oa-attachment-raw-payload-repairer-extraction-2026-06-25.md`.
- `WorkbenchCanonicalOaAttachmentRawPayloadRepairer` now owns payload OA scan/imported invoice iteration/append-vs-replace/dedupe-summary orchestration.
- Source-link parsing, canonical row construction and raw payload helper extraction remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-canonical-oa-attachment-raw-payload-repairer-extraction` is complete:

- added `WorkbenchCanonicalOaAttachmentRawPayloadRepairer`;
- moved payload OA scan/imported invoice iteration/append-vs-replace/dedupe-summary orchestration out of `_append_canonical_oa_attachment_invoice_rows(...)`;
- kept source-link parsing, canonical row construction, replacement, dedupe and summary refresh as explicit ports;
- preserved repair behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-oa-attachment-source-link-resolver-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-canonical-oa-attachment-raw-payload-repairer-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` and `tests/test_workbench_v2_api.py` raw payload, OA retention and relation repair tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_oa_attachment_source_link_for_invoice(...)`;
   - `_source_oa_id_for_attachment_link(...)`;
   - source link normalization;
   - `oa_attachment_best_source_link` / `oa_attachment_matches_oa` usage.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
