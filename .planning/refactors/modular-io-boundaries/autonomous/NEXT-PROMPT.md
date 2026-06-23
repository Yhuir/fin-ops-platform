# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:pending-invoice-and-oa-pending-payment-contract`
- Last status: `closed-autonomous`
- Pending invoice is guarded as a page-first-screen scoped read model that rejects bare `all`; OA pending payment is guarded as a fan-out `all` read model with separate repository/detail ports.

## Next Boundary

`read-models:invoice-lifecycle-and-usage-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/product-specs/invoice-lifecycle.md`
   - `docs/modules/domain-events-lifecycle/README.md`
   - `docs/modules/domain-events-lifecycle/state-machine.md`
   - `docs/modules/domain-events-lifecycle/tests.md`
   - `docs/modules/input-invoice-usage/README.md`
   - `docs/modules/input-invoice-usage/state-machine.md`
   - `docs/modules/input-invoice-usage/tests.md`
   - `docs/modules/output-invoice-collections/README.md`
   - `docs/modules/output-invoice-collections/state-machine.md`
   - `docs/modules/output-invoice-collections/tests.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-and-oa-pending-payment-contract.md`
4. Use CodeGraph for `InvoiceLifecycleReadFacade`, `InvoiceLifecycleReadModelRefreshService`, `InputInvoiceUsageReadModelService`, `OutputInvoiceCollectionService`, `InvoiceUsageCollectionReadModelRefreshService`, invoice usage repository methods, relation source version reads, and production fail-closed behavior for missing SQL repositories.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-and-usage-contract.md`.
6. If implementation starts in that boundary, keep it to invoice lifecycle / input usage / output collection manifest contract tests, owner refinement, or one tiny guard. Do not rewrite import processing, invoice lifecycle business policy, worker rebuild, Go/Fiber, Go Worker, or production state.

## Stop Condition

Complete one narrow verified invoice lifecycle / invoice usage contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
