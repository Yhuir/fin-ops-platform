# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:server-relation-read-helper-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:server-relation-read-helper-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Remaining `server.py` direct relation read/snapshot helpers are classified.
- Workbench page payload/live-row active relation reads are the next smallest safe extraction boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:server-workbench-payload-relation-read-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-relation-read-helper-boundary-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph/text search for `_apply_pair_relations_to_payload`, `_supplement_missing_active_pair_relation_rows`, `_relation_for_group`, `_resolve_live_rows_direct`, `get_active_relation_by_row_id`, and `list_active_relations`.
7. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add an explicit server-side Workbench payload relation read port for active relation reads used by payload/live-row enrichment.
- Move these direct pair service calls behind the port:
  - `_apply_pair_relations_to_payload(...)`
  - `_supplement_missing_active_pair_relation_rows(...)`
  - `_relation_for_group(...)`
  - `_resolve_live_rows_direct(...)`
- Preserve returned row/group payload shape, pair relation projection, missing row supplementation and override application behavior.
- Add static guard coverage focused on the extracted payload enrichment methods.

Forbidden:

- Do not change repair/write precondition reads in this slice.
- Do not change source-version snapshot reads in this slice.
- Do not change transaction-persist, rollback or whole-state persistence snapshot reads in this slice.
- Do not change relation writes, command service behavior, matching rules, dirty scopes, read model refresh, API response shape or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated analysis/docs/state/queue/journal/next prompt.
- Focused Workbench payload/API regression tests and static guard.
- App check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:server-workbench-payload-relation-read-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
