# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `reconciliation-workbench:amount-check-query-contract`
- Last status: `closed-autonomous`
- Workbench amount-check now has a regression guard proving explicit `reconciliation_amount` wins over legacy `detail_fields.明细金额合计` fallback. The legacy fallback remains compat-only and must not pollute the new query/read payload path.

## Next Boundary

`batch-accounting:legacy-route-contract`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `docs/modules/batch-accounting/README.md`
   - `docs/modules/batch-accounting/state-machine.md`
   - `docs/modules/batch-accounting/tests.md`
   - `docs/modules/batch-accounting/implementation-notes.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/state-machine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/reconciliation-workbench-amount-check-query-contract.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
4. Use CodeGraph for batch accounting route handlers, application/service owners, relation command/write boundaries, Workbench relation fan-out, read model refresh enqueue paths, permission checks, and tests protecting submit/withdraw behavior.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-legacy-route-contract.md`.
6. Keep implementation narrow: add or tighten one route/service/read-model/legacy contamination guard, owner manifest entry, or analysis-backed contract test. Do not do a broad `server.py` split, do not change business semantics, do not implement Go/Fiber or Go Worker, and do not change production state.

## Stop Condition

Complete one narrow verified batch-accounting legacy route contract slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
