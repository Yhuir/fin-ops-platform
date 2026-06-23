# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:cost-tax-ledger-summary-contract`
- Last status: `closed-autonomous`
- Cost statistics is guarded as a queryable parent aggregate read model; tax offset and turnover ledger are guarded as fan-out/incremental read models with explicit worker/query/permission owners and disjoint repository ports.

## Next Boundary

`read-models:search-and-no-oa-bank-batch-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/product-specs/bank-turnover-and-no-oa.md`
   - `docs/modules/no-oa-bank-batches/README.md`
   - `docs/modules/no-oa-bank-batches/state-machine.md`
   - `docs/modules/no-oa-bank-batches/tests.md`
   - `docs/modules/no-oa-bank-batches/implementation-notes.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-tax-ledger-summary-contract.md`
4. Use CodeGraph for `Search read API`, `SearchPendingReadModelRefreshService`, `NoOaBankBatchApplicationService`, `NoOaBankBatchReadModelRefreshService`, search/no-OA repository methods, query gateway ownership, scope policy entries, freshness/status handling, and production fail-closed behavior.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-search-and-no-oa-bank-batch-contract.md`.
6. If implementation starts in that boundary, keep it to search / no-OA bank batch manifest contract tests, owner refinement, or one tiny guard. Do not rewrite search indexing, no-OA business batch writes, worker rebuild, Go/Fiber, Go Worker, or production state.

## Stop Condition

Complete one narrow verified search / no-OA bank batch read-side contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
