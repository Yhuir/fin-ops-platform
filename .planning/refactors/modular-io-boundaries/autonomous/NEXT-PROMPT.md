# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:route-owner-inventory`
- Last status: `closed-autonomous`
- `server.py` route owner inventory now has a static guard: every existing `routes_*.py` owner must be registered in the manifest test, imported by `server.py`, and have a factory/accessor or attribute delegate marker. This is a no-runtime-change boundary.

## Next Boundary

`go-hot-path:workbench-compute-admission`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Read:
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-route-owner-inventory.md`
   - `.planning/refactors/modular-io-boundaries/analysis/reconciliation-workbench-amount-check-query-contract.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/state-machine.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/reconciliation-workbench/implementation-notes.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/runtime-workers/README.md`
   - `docs/modules/runtime-workers/state-machine.md`
4. Use CodeGraph first to locate Workbench matching/grouping/check compute owners, callers, read model builder boundaries, worker entry points, and existing tests.
5. Produce `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-admission.md`.
6. Fill the Go candidate admission table from `05-IMPACT-AND-TEST-GATES.md` and `11-GO-HOT-PATH-CARVE-OUT.md`.
7. Do not implement Go/Fiber/Go Worker in this boundary. This is admission review only.

## Admission Decision Rules

- Candidate key must be `workbench:matching-grouping-check`.
- If performance evidence, IO contract, shadow-run feasibility, Python-vs-Go equivalence tests, rollback plan, freshness proof, or legacy isolation is missing, mark the boundary `go-candidate-deferred`.
- If every admission gate is satisfied without production writes, record the evidence and queue a future implementation boundary. Do not implement Go in the admission slice.
- Missing local `PGSQL_URL` or staging DB is not a hard blocker; record the exact evidence gap.
- Production SSH may be used only for non-secret read-only evidence such as service status, code/version files, or logs without credentials. Do not read secrets and do not perform production writes.

## Stop Condition

Complete one narrow verified admission slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
