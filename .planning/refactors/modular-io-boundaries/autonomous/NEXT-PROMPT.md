# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:post-workbench-write-facade-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:post-workbench-write-facade-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- WorkbenchWriteFacade now requires explicit relation read/snapshot and special metadata mutation ports.
- WorkbenchWriteFacade no longer stores or accepts broad `pair_relation_service`.
- ETC repair/link/migration services are already command-boundary guarded and are not the next highest-risk local gap.
- `TurnoverLedgerWorkbenchPairPort` still accepts and stores broad `pair_relation_service`; this is the next narrow implementation boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:turnover-workbench-pair-port-required-command-constructor`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-workbench-write-facade-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect:
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_turnover_ledger_uow_contract.py`
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph/text search for `TurnoverLedgerWorkbenchPairPort`, `pair_relation_service`, `_pair_relation_service`, and turnover builder/fallback construction.
7. Produce or update an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Remove `pair_relation_service` from `TurnoverLedgerWorkbenchPairPort.__init__`.
- Make `TurnoverLedgerWorkbenchPairPort` rely on explicit command service and relation facade boundaries only.
- Remove the port's pair-service fallback read path.
- Update turnover primary builder and legacy fallback facade construction so they no longer pass broad pair service into `TurnoverLedgerWorkbenchPairPort`.
- Keep builder-level pair service only where still required for local transaction snapshot/rollback via `TurnoverLedgerLocalClosureConnection`.
- Strengthen or add static guard coverage so the port cannot re-accept or store broad pair service.

Forbidden:

- Do not remove `TurnoverLedgerLocalClosureConnection` pair snapshot rollback behavior in this slice.
- Do not change turnover relation business rules, amount rules, affected month scope rules, dirty outbox behavior, operation barrier behavior or API response shape.
- Do not change ETC behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated analysis/docs/state/queue/journal/next prompt.
- Targeted tests for turnover pair port and static boundary guards.
- `python3 -m fin_ops_platform.app.main --check`, docs verification, and `git diff --check` as applicable.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:turnover-workbench-pair-port-required-command-constructor` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
