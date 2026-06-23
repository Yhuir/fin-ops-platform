# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:server-oa-attachment-repair-relation-read-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:server-oa-attachment-repair-relation-read-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- OA attachment context repair active relation reads now go through `WorkbenchOaAttachmentRepairRelationReadPort`.
- Remaining write-adjacent reads include confirm-link context expansion and auto-pair conflict checks.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:server-confirm-link-context-relation-read-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-oa-attachment-repair-relation-read-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph/text search for `_expand_confirm_link_row_ids_for_existing_context`, `active_relations_for_row_ids`, and `confirm-link`.
7. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add or reuse an explicit relation read port for confirm-link context expansion active relation reads.
- Move `_expand_confirm_link_row_ids_for_existing_context(...)` direct active relation reads behind that port.
- Preserve row-id normalization, related context expansion, self-row exclusion, existing relation scope semantics, and confirm-link behavior.
- Add static guard coverage for this method.
- Run the closest Workbench V2 confirm-link/API regression tests plus app check.

Forbidden:

- Do not change `_auto_pair_conflicts_with_manual_relation(...)`.
- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated analysis/docs/state/queue/journal/next prompt.
- Focused confirm-link/static guard tests.
- App check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:server-confirm-link-context-relation-read-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
