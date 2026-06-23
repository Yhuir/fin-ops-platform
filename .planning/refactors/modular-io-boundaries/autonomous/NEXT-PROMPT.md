# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:post-server-precondition-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:post-server-precondition-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:server-retained-oa-supplemental-relation-read-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-server-precondition-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `_supplemental_retained_oa_row_ids`, `list_active_relations`, retained OA rows, and all-scope payload tests.
6. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add or reuse an explicit relation read port for retained-OA all-scope supplemental relation reads.
- Move `_supplemental_retained_oa_row_ids(...)` direct `list_active_relations()` call behind that port.
- Preserve cutoff date behavior, manual retained row ids, OA/bank relation filtering, bank row date checks, and sorted returned row ids.
- Add static guard coverage for this method.
- Run the closest retained-OA Workbench API regression tests plus app check.

Forbidden:

- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated analysis/docs/state/queue/journal/next prompt.
- Focused retained-OA/static guard tests.
- App check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:server-retained-oa-supplemental-relation-read-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
