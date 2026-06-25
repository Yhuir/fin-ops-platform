# Next Prompt

Continue after `server-py:workbench-oa-invoice-offset-sync-executor-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-oa-invoice-offset-sync-executor-extraction`.
- Row457 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-invoice-offset-sync-executor-extraction-2026-06-25.md`.
- `WorkbenchOaInvoiceOffsetSyncExecutor` now owns auto-pair confirm/cancel/persist/lifecycle orchestration.
- OA attachment repair context remains deferred to a dedicated slice.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-oa-invoice-offset-sync-executor-extraction` is complete:

- added `WorkbenchOaInvoiceOffsetSyncExecutor`;
- moved OA invoice offset relation sync orchestration out of `Application`;
- preserved existing `Application` helper name as a delegate;
- preserved unchanged, confirm, cancel and out-of-current-payload no-cancel behavior;
- updated static Guards and local tests;
- avoided production validation.

## Next Boundary

`server-py:workbench-oa-attachment-repair-context-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-invoice-offset-sync-executor-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/server.py` around `_repair_active_relations_with_oa_attachment_context(...)`
   - related Workbench OA attachment repair tests in `tests/test_workbench_v2_api.py`
   - relevant static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining OA attachment repair context side effects:
   - active relation lookup;
   - source link/derived OA row matching;
   - command service calls;
   - changed case id and scope collection;
   - pair relation persistence;
   - derived lifecycle event emission.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from this executor extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move OA attachment repair side effects without regression tests for unchanged and repaired active relation behavior.
