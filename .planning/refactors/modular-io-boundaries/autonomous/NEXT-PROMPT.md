# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:invoice-lifecycle-and-usage-contract`
- Last status: `closed-autonomous`
- Invoice lifecycle, input invoice usage and output invoice collection are guarded as scoped incremental fan-out read models with explicit worker/query/permission owners and disjoint repository ports.

## Next Boundary

`read-models:cost-tax-ledger-summary-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/product-specs/cost-tax.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/cost-statistics/state-machine.md`
   - `docs/modules/cost-statistics/tests.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/state-machine.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-and-usage-contract.md`
4. Use CodeGraph for `CostStatisticsQueryService`, `TaxOffsetQueryService`, `TurnoverLedgerQueryService`, cost/tax/turnover repository methods, query gateway ownership, scope policy entries, parent/fan-out semantics, and production fail-closed behavior.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-tax-ledger-summary-contract.md`.
6. If implementation starts in that boundary, keep it to cost statistics / tax offset / turnover ledger manifest contract tests, owner refinement, or one tiny guard. Do not rewrite rollup SQL, tax certification business policy, turnover relation writes, worker rebuild, Go/Fiber, Go Worker, or production state.

## Stop Condition

Complete one narrow verified cost/tax/turnover ledger summary contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
