# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:query-gateway-contract-and-status-parity`
- Last status: `closed-autonomous`
- A code-level read model manifest now covers the 14 App Status read model keys and is guarded against App Status registry, worker registry, RabbitMQ dispatch, and scope policy drift.

## Next Boundary

`read-models:refresh-gateway-force-refresh-and-operation-barrier`

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
4. Use CodeGraph for `ReadModelRefreshGateway`, `ReadModelScopePolicyRegistry`, `OperationFreshnessBarrierService`, direct refresh producers, transaction dirty/outbox producers, and force-refresh/runbook/API entry points.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-refresh-gateway-force-refresh-and-operation-barrier.md`.
6. If implementation starts in that boundary, keep it to refresh/barrier contract tests and small registry/manifest wiring first; do not implement Go/Fiber, Go Worker, production writes, or broad SQL splitting.

## Stop Condition

Complete one narrow verified refresh/force-refresh/operation-barrier slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
