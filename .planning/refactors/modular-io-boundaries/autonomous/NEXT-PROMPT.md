# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:post-no-oa-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:post-no-oa-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- No-OA application snapshot/version/persist/rollback pair service usage goes through `NoOaPairRelationSnapshotPort`.
- No-OA domain repair/read active relation reads go through `NoOaRelationRepairReadPort`.
- WorkbenchWriteFacade remains the largest direct broad pair service holder.
- ETC still needs later focused classification, but it is not the highest-risk next boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:workbench-write-facade-pair-service-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-no-oa-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_workbench_write_characterization.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `_pair_relation_service`, `active_relations_for_row_ids`, `get_active_relation_by_row_id`, `snapshot`, `update_special_metadata_for_row_ids`, `clear_special_metadata_for_row_ids`, `preview_withdraw_for_row_ids`, `relation_command_service`, `relation_command_service_factory`, `restore_pair_relation_snapshot`, and `persist_pair_relations`.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit every `WorkbenchWriteFacade._pair_relation_service` call site.
- Classify each call as command write, read/preflight, snapshot/rollback, special metadata mutation, or compat-only.
- Identify which call sites are already command-service gated and which still bypass the target boundary.
- Decide the next narrow implementation boundary; do not migrate the whole facade in one slice.
- Preserve Workbench confirm/cancel/withdraw/idempotency/UoW behavior.
- Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not change relation write semantics, API payloads, dirty scope semantics, read model refresh semantics or Workbench active generation semantics in this audit slice.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:workbench-write-facade-pair-service-boundary-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
