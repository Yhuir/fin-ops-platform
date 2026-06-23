# Next Prompt

Continue the autonomous modular IO refactor from the paused state.

## Current State

- Branch: `dev`
- Last completed boundary: `bank-details:auto-tag-category-boundary`
- Last status: `production-evidence-deferred`
- The queue has been reprioritized so read model foundation runs before additional page-specific slices.
- Do not continue to another module unless the user asks to resume.

## Next Boundary

`read-models:manifest-and-boundary-inventory`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-modularization-pre-analysis.md`
4. Use CodeGraph for `ReadModelQueryGateway`, `ReadModelRefreshGateway`, `ReadModelScopePolicyRegistry`, `APP_STATUS_READ_MODEL_REGISTRY`, `runtime_worker_registry`, `operation_freshness_barrier`, and `postgres_repositories/read_models.py`.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`.
6. Do not implement Go/Fiber, Go Worker, production writes, or broad SQL splitting in this boundary.

## Stop Condition

Complete the read model manifest/owner/IO/state/event/permission/test inventory, update docs/state, commit and push to `origin/dev`, then continue only if the user has explicitly resumed autonomous execution.
