# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:server-retained-oa-supplemental-relation-read-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:server-retained-oa-supplemental-relation-read-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Retained-OA supplemental relation reads now go through `WorkbenchRetainedOaSupplementalRelationReadPort`.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:server-case-id-allocation-relation-read-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-retained-oa-supplemental-relation-read-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-server-precondition-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_relation_command_service.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `_next_workbench_relation_case_id`, relation snapshot case ids, confirm-link case id allocation and collision tests.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit `_next_workbench_relation_case_id(...)` direct relation snapshot read.
- Decide whether the next safe boundary is a case-id allocation read port/service extraction or a narrower guard/accounting slice.
- Preserve case-id collision avoidance and confirm-link behavior.
- Do not implement until the ownership boundary is clear.

Forbidden:

- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior during the audit.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Analysis/accounting slice.
- Updated queue/state/journal/next prompt.
- Docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:server-case-id-allocation-relation-read-owner-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
