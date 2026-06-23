# Next Prompt

Continue the autonomous modular IO refactor from the selected `bank_detail` read model pilot.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:pilot-gap-audit-and-contract-selection`
- Last status: `analysis-closed`
- Queue semantics are corrected: prior guard/analysis slices are slice-complete only and do not mean module implementation closure.
- First read model implementation pilot: `bank_detail`.
- Go hot-path candidates are blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-repository-port-extraction`

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
   - Read `.planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md`.
   - Read `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`.
   - Read `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
   - If these files disagree on current state, next boundary, status labels, module closure meaning or completion metric source, stop normal implementation and create another `planning:state-reconciliation-*` slice first.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/planning-state-reconciliation.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-modularization-pre-analysis.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-query-gateway-contract-and-status-parity.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-refresh-gateway-force-refresh-and-operation-barrier.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/runtime-workers/README.md`
   - `docs/modules/runtime-workers/state-machine.md`
5. Read `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md`.
6. Use CodeGraph first to locate current `bank_detail` query/refresh/repository owners, callers, callees, routes and tests.
7. Implement the narrow `bank_detail` repository port/query boundary without changing response shape.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Selection Rules

- The pilot is already selected: `bank_detail`.
- Do not choose a Go boundary.
- Do not implement Go/Fiber/Go Worker in this boundary.
- Do not claim a module is closed because a manifest guard or static guard exists.
- Treat `closed` module implementation status as unavailable unless code, tests, docs, legacy isolation/removal, freshness proof, operation barrier, force refresh and production evidence/defer status are all accounted for.
- If implementation exposes a larger scope than the selected boundary, stop normal implementation and create a narrower planning or guard slice instead of broad refactoring.

## Expected Output

- Implementation file changes for `bank_detail` repository port/query boundary only.
- Tests proving the API/query boundary uses the `bank_detail` port and preserves response shape.
- Legacy contamination guard or regression evidence proving the new path does not reach unrelated read model repository methods.
- Updated state/journal/next prompt.
- Docs verification and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one narrow verified `bank_detail` implementation slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
