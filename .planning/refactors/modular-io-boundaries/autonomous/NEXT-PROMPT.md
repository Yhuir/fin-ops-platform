# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:server-repair-precondition-relation-read-port-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:server-repair-precondition-relation-read-port-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- OA invoice offset sync, OA attachment context repair, confirm-link context expansion and auto-pair conflict checks are classified as separate write-adjacent read surfaces.
- The next smallest safe implementation boundary is OA invoice offset sync relation read port extraction.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:server-oa-invoice-offset-relation-read-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-repair-precondition-relation-read-port-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_v2_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph/text search for `_sync_oa_invoice_offset_auto_pair_relations`, `OA_INVOICE_OFFSET_AUTO_MATCH_MODE`, `list_active_relations`, `WorkbenchRelationCommandService`, and the OA invoice offset sync tests.
7. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add or reuse an explicit relation read port for OA invoice offset auto-pair sync precondition reads.
- Move `_sync_oa_invoice_offset_auto_pair_relations(...)` direct `list_active_relations()` call behind that port.
- Preserve filtering by `OA_INVOICE_OFFSET_AUTO_MATCH_MODE`, create/cancel behavior, changed case ids, changed scope keys, derived lifecycle event metadata and persistence scheduling.
- Add static guard coverage for this method.
- Run existing OA invoice offset sync tests.

Forbidden:

- Do not change `_repair_active_relations_with_oa_attachment_context(...)`.
- Do not change `_expand_confirm_link_row_ids_for_existing_context(...)`.
- Do not change `_auto_pair_conflicts_with_manual_relation(...)`.
- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated analysis/docs/state/queue/journal/next prompt.
- Focused OA invoice offset sync regression tests and static guard.
- App check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:server-oa-invoice-offset-relation-read-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
