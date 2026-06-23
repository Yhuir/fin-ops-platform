# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:turnover-workbench-pair-port-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:turnover-workbench-pair-port-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Turnover pair writes are command-service gated.
- `TurnoverLedgerWorkbenchPairPort.pair_relation_service` is currently classified as read-only compat fallback.
- `TurnoverLedgerWorkbenchPairPort.persist_pair_relations` is unused wiring and should be removed next.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:turnover-workbench-pair-port-unused-persist-callback-removal`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-workbench-pair-port-boundary-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - `tests/test_turnover_ledger_uow_contract.py`
   - `tests/test_platform_runtime_boundary_guards.py`
5. Use CodeGraph/text search for `TurnoverLedgerWorkbenchPairPort`, `persist_pair_relations`, `_persist_pair_relations`, and caller wiring.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Remove the unused `persist_pair_relations` constructor parameter from `TurnoverLedgerWorkbenchPairPort`.
- Remove the unused `_persist_pair_relations` field.
- Remove `persist_pair_relations=...` arguments from primary builders and legacy fallback facades where they instantiate the port.
- Keep `pair_relation_service` read-only compat fallback unchanged.
- Update static guard to prove `_persist_pair_relations` cannot return inside `TurnoverLedgerWorkbenchPairPort`.

Forbidden:

- Do not remove `pair_relation_service` in this slice.
- Do not change turnover closure/withdraw/cash-closure business rules.
- Do not change API payloads, dirty scope semantics, read model refresh semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Narrow implementation slice.
- Updated analysis/accounting file for the implementation.
- Updated docs/state/queue/journal/next prompt.
- Targeted turnover/guard tests, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:turnover-workbench-pair-port-unused-persist-callback-removal` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
