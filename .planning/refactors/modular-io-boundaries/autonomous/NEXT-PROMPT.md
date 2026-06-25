# Next Prompt

Continue after `server-py:workbench-oa-invoice-offset-rebuild-helper-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-oa-invoice-offset-rebuild-helper-extraction`.
- Row453 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-invoice-offset-rebuild-helper-extraction-2026-06-25.md`.
- `WorkbenchOaInvoiceOffsetRebuildHelper` now owns cached payload rebuild detection and attachment invoice row filtering.
- OA invoice offset desired relation sync orchestration remains deferred to a dedicated slice.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-oa-invoice-offset-rebuild-helper-extraction` is complete:

- added `WorkbenchOaInvoiceOffsetRebuildHelper`;
- moved cached payload rebuild detection out of `Application`;
- moved attachment invoice row filtering out of `Application`;
- preserved existing `Application` helper names as delegates;
- preserved OA invoice offset cache-read behavior with local tests;
- added static Guard coverage;
- avoided production validation.

## Next Boundary

`server-py:workbench-oa-invoice-offset-relation-sync-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-invoice-offset-rebuild-helper-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/server.py` around `_sync_oa_invoice_offset_auto_pair_relations(...)`, `_oa_invoice_offset_desired_relations(...)`, `_month_scope_for_oa_invoice_offset_relation(...)`
   - related Workbench OA invoice offset tests in `tests/test_workbench_v2_api.py`
   - relevant static guards in `tests/test_platform_runtime_boundary_guards.py`
3. Audit remaining OA invoice offset relation sync surfaces:
   - desired relation construction;
   - existing relation read port usage;
   - manual-conflict checks;
   - month scope derivation;
   - create/cancel side effects and history operation labels.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from this helper extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move relation sync side effects without a dedicated implementation analysis and regression tests.
