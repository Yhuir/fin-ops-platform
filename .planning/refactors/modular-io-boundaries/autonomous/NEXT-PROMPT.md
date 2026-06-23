# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:workbench-active-generation-contract`
- Last status: `closed-autonomous`
- Workbench is explicitly guarded as an active-generation special read model and must not be mechanically converted to a generic read model rebuild/gateway path.

## Next Boundary

`read-models:bank-detail-and-bank-account-balance-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/state-machine.md`
   - `docs/modules/bank-details/tests.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-workbench-active-generation-contract.md`
4. Use CodeGraph for `BankDetailsApplicationService`, `BankTransactionTagReadFacade`, `BankDetailReadModelRefreshService`, `BankAccountBalanceProjectionBuilder`, bank detail repository methods in `PostgresReadModelRepository`, auto-tag rule source versions, and operation barrier usage from the bank details page.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-and-bank-account-balance-contract.md`.
6. If implementation starts in that boundary, keep it to bank detail / bank account balance contract tests, manifest owner refinement, or one tiny guard. Do not rewrite import processing, auto-tag business rules, worker rebuild, Go/Fiber, Go Worker, or production state.

## Stop Condition

Complete one narrow verified bank detail / bank account balance contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
