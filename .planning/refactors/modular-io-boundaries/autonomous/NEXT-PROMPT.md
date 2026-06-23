# Next Prompt

Continue the autonomous modular IO refactor from the paused state.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:manifest-and-boundary-inventory`
- Last status: `closed-autonomous`
- Read model foundation inventory is complete; continue with query/status parity before page-specific slices.
- Do not continue to another module unless the user asks to resume.

## Next Boundary

`read-models:query-gateway-contract-and-status-parity`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
4. Use CodeGraph for `ReadModelQueryGateway`, self-managed freshness services, direct `read_model_status=fresh` paths, direct refresh producers, and legacy/live-scan fallbacks.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-query-gateway-contract-and-status-parity.md`.
6. If implementation starts in that boundary, keep it to manifest/parity guards and query/status contract tests first; do not implement Go/Fiber, Go Worker, production writes, or broad SQL splitting.

## Stop Condition

Complete one narrow verified query/status parity slice, update docs/state, commit and push to `origin/dev`, then continue only if the user has explicitly resumed autonomous execution.
