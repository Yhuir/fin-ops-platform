# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:legacy-read-path-removal-guards`
- Last status: `closed-autonomous`
- Direct `enqueue_read_model_refresh(...)` call sites are now statically classified. New non-gateway refresh producers must be removed, moved behind `ReadModelRefreshGateway`, or explicitly quarantined with owner/reason/deletion condition.

## Next Boundary

`reconciliation-workbench:amount-check-query-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/state-machine.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/reconciliation-workbench/implementation-notes.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-legacy-read-path-removal-guards.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
4. Use CodeGraph for Workbench matching/grouping/check query contracts, amount-check calculation entry points, Workbench active generation query facade, repository methods, route owners, freshness/status handling, and tests protecting amount mismatch behavior.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/reconciliation-workbench-amount-check-query-contract.md`.
6. Keep implementation narrow: add or tighten an amount-check query/compute contract guard, owner manifest entry, or one small route/service boundary guard. Do not rewrite Workbench, do not change matching business semantics, do not implement Go/Fiber or Go Worker, and do not change production state.

## Stop Condition

Complete one narrow verified Workbench amount-check query contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
