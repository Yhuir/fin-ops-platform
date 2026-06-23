# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:app-health-route-builder-pair-service-injection-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:app-health-route-builder-pair-service-injection-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Turnover primary builders still pass broad pair service into local snapshot/restore support.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:turnover-local-pair-snapshot-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-app-health-route-builder-pair-service-injection-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-workbench-pair-port-required-command-constructor.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
4. Inspect:
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - turnover ledger API/service tests that cover local rollback.
5. Use CodeGraph/text search for `TurnoverLedgerLocalClosureConnection`, `TurnoverLedgerConfirmPrimaryWriteFacadeBuilder`, `TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder`, `pair_relation_service`, `_pair_relation_service`, `snapshot`, `from_snapshot`, and turnover rollback tests.
6. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Add or reuse an explicit turnover local pair snapshot/restore port.
- Remove broad `pair_relation_service` from turnover primary builder constructors and `TurnoverLedgerLocalClosureConnection`.
- Preserve local transaction rollback semantics for confirm/withdraw.
- Preserve command-service writes, relation facade reads and route response shape.
- Add or update static guard coverage proving turnover primary builders/local connection no longer accept broad pair service.
- Do not mark the module closed unless local evidence proves all implementation gaps are closed.

Forbidden:

- Do not change relation writes, read model freshness, dirty scopes, operation barriers, API response shape or frontend behavior beyond the narrow turnover local snapshot/restore port extraction.
- Do not implement Go/Fiber/Go Worker.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Narrow implementation slice.
- Updated queue/state/journal/next prompt.
- Targeted turnover/guard tests, docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:turnover-local-pair-snapshot-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
