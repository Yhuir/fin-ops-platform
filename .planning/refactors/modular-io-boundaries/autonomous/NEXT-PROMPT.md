# Next Prompt

Continue after `server-py:workbench-oa-attachment-source-link-resolver-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-oa-attachment-source-link-resolver-extraction`.
- Row439 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-attachment-source-link-resolver-extraction-2026-06-25.md`.
- `WorkbenchOaAttachmentSourceLinkResolver` now owns source link filtering/normalization, `oa_form_id` fallback, best-link selection and source OA id matching.
- Canonical row construction and raw payload helper extraction remain deferred to dedicated slices.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-oa-attachment-source-link-resolver-extraction` is complete:

- added `WorkbenchOaAttachmentSourceLinkResolver`;
- moved source link filtering/normalization, `oa_form_id` fallback, best-link selection and source OA id matching out of `Application`;
- preserved existing `Application` method names as compatibility delegates;
- preserved source-link behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-canonical-oa-attachment-invoice-row-builder-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-attachment-source-link-resolver-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/app/server.py` remaining Workbench read/support surfaces
   - `tests/test_workbench_sql_runtime.py` and `tests/test_workbench_v2_api.py` raw payload, OA retention and relation repair tests
   - relevant Workbench static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining Workbench read/support surfaces:
   - `_canonical_oa_attachment_invoice_workbench_row(...)`;
   - invoice field mapping;
   - tags and detail fields;
   - relation payload construction.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from Workbench read route-owner extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move legacy `/api/workbench` SQL fallback without a dedicated implementation analysis and freshness tests.
