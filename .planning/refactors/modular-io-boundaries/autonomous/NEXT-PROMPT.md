# Next Prompt

Continue the autonomous modular IO refactor from the current state.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:state-reconciliation-and-roadmap-alignment`
- Last status: `closed-autonomous`
- Planning state has been reconciled: `.planning/ROADMAP.md` is the page-analysis roadmap, `04-IMPLEMENTATION-ROADMAP.md` is the modular IO phase roadmap, and `autonomous/MODULE-QUEUE.md` is the executable boundary queue. Completion percentages must always state which source they use.

## Next Boundary

`go-hot-path:workbench-compute-admission`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only`.
3. Perform planning-state preflight:
   - Read `.planning/ROADMAP.md`.
   - Read `.planning/refactors/README.md`.
   - Read `.planning/refactors/modular-io-boundaries/README.md`.
   - Read `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`.
   - Read `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`.
   - Read `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
   - If these files disagree on current state, next boundary, status labels or completion metric source, stop normal implementation and create another `planning:state-reconciliation-*` slice first.
4. Read:
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
   - `.planning/refactors/modular-io-boundaries/analysis/planning-state-reconciliation.md`
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
5. Use CodeGraph first to locate Workbench matching/grouping/check compute owners, callers, read model builder boundaries, worker entry points, and existing tests.
6. Produce `.planning/refactors/modular-io-boundaries/analysis/go-hot-path-workbench-compute-admission.md`.
7. Fill the Go candidate admission table from `05-IMPACT-AND-TEST-GATES.md` and `11-GO-HOT-PATH-CARVE-OUT.md`.
8. Do not implement Go/Fiber/Go Worker in this boundary. This is admission review only.

## Admission Decision Rules

- Candidate key must be `workbench:matching-grouping-check`.
- If performance evidence, IO contract, shadow-run feasibility, Python-vs-Go equivalence tests, rollback plan, freshness proof, or legacy isolation is missing, mark the boundary `go-candidate-deferred`.
- If every admission gate is satisfied without production writes, record the evidence and queue a future implementation boundary. Do not implement Go in the admission slice.
- Missing local `PGSQL_URL` or staging DB is not a hard blocker; record the exact evidence gap.
- Production SSH may be used only for non-secret read-only evidence such as service status, code/version files, or logs without credentials. Do not read secrets and do not perform production writes.

## Stop Condition

Complete one narrow verified admission slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.

Do not report a single unqualified percentage for "the whole refactor plan".
