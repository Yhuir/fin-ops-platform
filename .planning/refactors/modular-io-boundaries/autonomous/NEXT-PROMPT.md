# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-and-bank-account-balance-contract`
- Last status: `closed-autonomous`
- Bank detail and account balance are guarded as separate read model contracts. `bank_detail:all` remains a fan-out command, while account balance keeps independent scope/event/repository/test ownership.

## Next Boundary

`read-models:pending-invoice-and-oa-pending-payment-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/state-machine.md`
   - `docs/modules/pending-invoices/tests.md`
   - `docs/modules/oa-pending-payments/README.md`
   - `docs/modules/oa-pending-payments/state-machine.md`
   - `docs/modules/oa-pending-payments/tests.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-and-bank-account-balance-contract.md`
4. Use CodeGraph for `PendingInvoiceReadModelService`, `OaPendingPaymentReadModelService`, pending invoice scope policy, OA pending payment repository methods, workbench relation source version reads, and production fail-closed behavior for missing SQL repositories.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-and-oa-pending-payment-contract.md`.
6. If implementation starts in that boundary, keep it to pending invoice / OA pending payment manifest contract tests, owner refinement, or one tiny guard. Do not rewrite import processing, relation matching, worker rebuild, Go/Fiber, Go Worker, or production state.

## Stop Condition

Complete one narrow verified pending invoice / OA pending payment contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
