# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:post-batch-restore-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:post-batch-restore-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Batch-accounting restore service delegation is locally complete.
- Post-batch audit found turnover, pending invoice, no-OA, ETC and WorkbenchWriteFacade relation dependencies still need focused classification.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:turnover-workbench-pair-port-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-batch-restore-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - relevant turnover/workbench relation tests.
5. Use CodeGraph/text search for `TurnoverLedgerWorkbenchPairPort`, turnover primary/fallback builders, `pair_relation_service`, `persist_pair_relations`, and relation command service factory callers/impact.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit `TurnoverLedgerWorkbenchPairPort` and turnover primary/fallback wiring.
- Decide whether the pair service dependency can be removed, should become command-service-only, or must remain `compat-only`.
- Classify primary write facade builders and legacy fallback facades separately.
- Produce an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not migrate turnover behavior in this audit slice unless a trivial no-code deletion is proven safe and queue is updated.
- Do not change turnover closure/withdraw business rules, API payloads, dirty scope semantics, read model refresh semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:turnover-workbench-pair-port-boundary-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
