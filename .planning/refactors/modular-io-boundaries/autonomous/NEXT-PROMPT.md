# Next Prompt

Continue after `server-py:workbench-pair-relation-display-policy-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:workbench-pair-relation-display-policy-extraction`.
- Row465 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-pair-relation-display-policy-extraction-2026-06-25.md`.
- `WorkbenchPairRelationDisplayPolicy` now owns relation display payload mapping.
- Pair relation row mutation and mode-specific metadata decorators remain deferred.
- Production browser/admin/write evidence remains deferred; no module/global closure is claimed.

## Previous Prompt Completion

`server-py:workbench-pair-relation-display-policy-extraction` is complete:

- added `WorkbenchPairRelationDisplayPolicy`;
- moved relation display payload mapping out of `Application`;
- preserved existing `Application` helper name as a delegate;
- preserved no-OA, internal transfer, salary, personal advance repayment, turnover closure, OA invoice offset and default display behavior;
- added static Guard and local tests;
- avoided production validation.

## Next Boundary

`server-py:workbench-pair-relation-row-mutation-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-pair-relation-display-policy-extraction-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `backend/src/fin_ops_platform/app/server.py` around `_apply_pair_relation_to_row(...)`, `_apply_oa_invoice_offset_pair_metadata(...)`, `_apply_cash_special_pair_metadata(...)`, `_apply_cash_special_available_actions(...)`, `_apply_internal_transfer_pair_metadata(...)`
   - relevant Workbench grouping/display tests and static guards
3. Audit pair relation row mutation:
   - relation field assignment;
   - relation metadata propagation;
   - amount check propagation;
   - available actions;
   - mode-specific decorators.
4. Select the next narrow local implementation or guard boundary.
5. If safe, implement with tests/Guard/docs; otherwise close the audit and select the next boundary.

## Stop Gates

- Do not run production validation or mutation.
- Do not claim global closure from this display policy extraction.
- Do not choose Go implementation; Go admission remains blocked.
- Do not move unrelated relation repair, grouping or route logic in this slice.
