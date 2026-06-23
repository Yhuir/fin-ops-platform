# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `batch-accounting:legacy-route-contract`
- Last status: `closed-autonomous`
- Batch-accounting route handlers now have a static boundary guard: GET must remain read-only through `BatchAccountingService.build_payload(...)`; submit/withdraw route handlers must enforce mutation session and delegate to `BatchAccountingService`, not direct relation write internals.

## Next Boundary

`server-py:route-owner-inventory`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-legacy-route-contract.md`
   - `.planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
   - `docs/app-architecture/runtime-and-ownership.md`
   - `docs/modules/README.md`
   - relevant module docs for any route owner selected by the inventory.
4. Use CodeGraph and AST/static tests to inventory residual `server.py` route ownership, but keep the implementation narrow.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/server-py-route-owner-inventory.md`.
6. Do not do a broad `server.py` split. Add or tighten one small inventory/guard only, with explicit legacy classification and no business/API behavior change.

## Stop Condition

Complete one narrow verified `server.py` route owner inventory slice, update docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
