# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:refresh-gateway-force-refresh-and-operation-barrier`
- Last status: `closed-autonomous`
- The read model manifest covers the 14 App Status read models and is guarded against App Status registry, worker registry, RabbitMQ dispatch, scope policy, force refresh smoke contract, and operation barrier target drift.

## Next Boundary

`read-models:repository-port-and-sql-owner-split-plan`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/architecture/persistence-and-read-models.md`
   - `docs/operations/runtime-worker-governance.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-query-gateway-contract-and-status-parity.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-refresh-gateway-force-refresh-and-operation-barrier.md`
4. Use CodeGraph for `PostgresReadModelRepository`, per-key read model repository methods, query facades/services that consume read model rows, and direct legacy read paths.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`.
6. If implementation starts in that boundary, keep it to repository owner inventory, port contracts, architecture guards, or one tiny low-risk extraction behind tests. Do not split the full `read_models.py` file in one pass, do not implement Go/Fiber or Go Worker, and do not perform production writes.

## Stop Condition

Complete one narrow verified repository-owner/port-contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
