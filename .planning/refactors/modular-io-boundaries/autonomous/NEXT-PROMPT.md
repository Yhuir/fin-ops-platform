# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:server-workbench-payload-relation-read-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:server-workbench-payload-relation-read-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Workbench payload/live-row active relation reads now go through `WorkbenchPayloadRelationReadPort`.
- Source-version relation snapshot reads are the next read model freshness boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:server-source-version-relation-snapshot-provider-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-workbench-payload-relation-read-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-server-relation-read-helper-boundary-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/workbench_read_model_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph/text search for `_no_oa_bank_batch_source_versions`, `_workbench_read_model_source_versions`, `pair_relation_snapshot_version`, `snapshot_version`, and `_workbench_pair_relation_service.snapshot`.
7. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Extract relation snapshot version reads used by Workbench/no-OA read model source-version freshness into an explicit provider.
- Move source-version direct pair service snapshot reads in:
  - `_no_oa_bank_batch_source_versions(...)`
  - `_workbench_read_model_source_versions(...)`
- Preserve exact `pair_relation_snapshot_version` values and payload shape.
- Add static guard coverage focused on source-version helpers.

Forbidden:

- Do not change page payload/live-row relation reads; they already use `WorkbenchPayloadRelationReadPort`.
- Do not change transaction-persist, rollback, repair/precondition, whole-state persistence or case-id allocation snapshot reads in this slice.
- Do not change read model freshness semantics, dirty scopes, operation barriers, API response shape or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated analysis/docs/state/queue/journal/next prompt.
- Focused source-version/static guard tests.
- App check, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:server-source-version-relation-snapshot-provider-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
