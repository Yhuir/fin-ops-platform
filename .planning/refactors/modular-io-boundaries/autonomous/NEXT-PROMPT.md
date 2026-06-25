# Next Prompt

Continue after `server-py:workbench-oa-invoice-offset-desired-relation-builder-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-oa-invoice-offset-desired-relation-builder-extraction`.
- Row455 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-invoice-offset-desired-relation-builder-extraction-2026-06-25.md`.
- `WorkbenchOaInvoiceOffsetDesiredRelationBuilder` now owns desired relation construction.
- OA invoice offset relation sync side effects remain deferred to a dedicated slice.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-oa-invoice-offset-desired-relation-builder-extraction` is complete:

- added `WorkbenchOaInvoiceOffsetDesiredRelationBuilder`;
- moved desired relation construction out of `Application`;
- preserved existing `Application` helper name as a delegate;
- preserved applicant filtering, attachment invoice row filtering, manual-conflict skip and month-scope behavior;
- added static Guard and local tests;
- avoided production validation.

## Next Boundary

`server-py:workbench-oa-invoice-offset-sync-executor-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-invoice-offset-desired-relation-builder-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/server.py` around `_sync_oa_invoice_offset_auto_pair_relations(...)`
   - related Workbench OA invoice offset tests in `tests/test_workbench_v2_api.py`
   - relation command service tests and relevant static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining OA invoice offset sync side effects:
   - active relation lookup;
   - desired-vs-active comparison;
   - confirm/cancel command calls;
   - changed case id collection;
   - changed scope collection;
   - pair relation persistence;
   - derived lifecycle event emission.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from this builder extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move side-effecting sync orchestration without regression tests for unchanged, confirm, cancel and out-of-current-payload cases.
