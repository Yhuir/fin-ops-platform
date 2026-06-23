# Next Prompt

Continue the autonomous modular IO refactor from the paused state.

## Current State

- Branch: `dev`
- Last completed boundary: `bank-details:auto-tag-category-boundary`
- Last status: `production-evidence-deferred`
- Do not continue to another module unless the user asks to resume.

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
4. Use CodeGraph for `amount_check`, workbench query/service route ownership, and legacy contamination paths before edits.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/reconciliation-workbench-amount-check-query-contract.md`.

## Stop Condition

Complete one narrow verified slice, update docs/state, commit and push to `origin/dev`, then continue only if the user has explicitly resumed autonomous execution.
