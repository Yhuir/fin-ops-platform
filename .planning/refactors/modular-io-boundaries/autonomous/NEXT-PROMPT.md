# Next Prompt

Continue after `server-py:workbench-oa-attachment-repair-context-executor-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-oa-attachment-repair-context-executor-extraction`.
- Row459 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-attachment-repair-context-executor-extraction-2026-06-25.md`.
- `WorkbenchOaAttachmentRepairContextExecutor` now owns missing OA attachment context repair confirm/persist/lifecycle orchestration.
- Lower-level OA attachment context row indexing remains deferred to a dedicated slice.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-oa-attachment-repair-context-executor-extraction` is complete:

- added `WorkbenchOaAttachmentRepairContextExecutor`;
- moved active relation missing-attachment repair orchestration out of `Application`;
- preserved existing `Application` helper name as a delegate;
- preserved no-op, dedicated-withdraw skip, replace-existing repair, before relation payload, amount check, persistence and lifecycle behavior;
- updated static Guards and local tests;
- avoided production validation.

## Next Boundary

`server-py:workbench-oa-attachment-context-row-index-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-attachment-repair-context-executor-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/server.py` around `_raw_workbench_payload_rows_by_id(...)`, `_oa_attachment_context_row_ids_by_oa_id(...)`, `_invoice_row_is_oa_attachment_context(...)`, `_oa_id_from_attachment_invoice_id(...)`
   - relevant static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining OA attachment context row-index helpers:
   - raw payload row indexing;
   - OA attachment invoice row detection;
   - derived OA id/source-link matching;
   - attachment invoice id fallback matching.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from this executor extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move unrelated relation display, grouping or row tag logic in this slice.
