# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:server-case-id-allocation-relation-read-owner-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:server-case-id-allocation-relation-read-owner-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:server-case-id-allocation-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-case-id-allocation-relation-read-owner-audit.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_workbench_write_characterization.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `_next_workbench_relation_case_id`, `next_case_id`, `CASE-AUTO-0001`, and case id collision behavior.
6. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add `WorkbenchRelationCaseIdAllocator`.
- Move relation snapshot parsing and used-case-id collision avoidance out of `Application._next_workbench_relation_case_id(...)`.
- Keep `Application._next_workbench_relation_case_id(...)` as a thin delegate or inject allocator method directly into `WorkbenchWriteFacade`.
- Preserve confirm-link auto case id behavior, especially skipping active `CASE-AUTO-0001`.
- Add static guard coverage.
- Run existing case-id collision characterization tests plus app check.

Forbidden:

- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated analysis/docs/state/queue/journal/next prompt.
- Focused case-id allocation/static guard tests.
- App check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:server-case-id-allocation-service-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
