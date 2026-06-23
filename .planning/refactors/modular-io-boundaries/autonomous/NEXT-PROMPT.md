# Next Prompt

Continue the autonomous modular IO refactor from the corrected queue semantics.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:completion-semantics-and-queue-reclassification`
- Last status: `planning-closed`
- Queue semantics have been corrected: prior guard/analysis slices are slice-complete only and do not mean module implementation closure.
- Go hot-path candidates are blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:pilot-gap-audit-and-contract-selection`

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
5. Use CodeGraph first to locate current read model query/refresh/repository owners, callers, callees, and tests for these pilot candidates:
   - `bank_detail`
   - `workbench_relation`
   - `pending_invoice`
   - `oa_pending_payment`
6. Produce `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md`.
7. Fill the selected pilot's current implementation gaps against `02-MODULE-IO-CONTRACT-TEMPLATE.md` and `05-IMPACT-AND-TEST-GATES.md`.
8. Select exactly one first implementation pilot and queue the exact next implementation boundary by updating `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file.

## Selection Rules

- Prefer the pilot that best reduces cross-page stale read model bugs while remaining small enough for one or two verified implementation slices.
- Do not choose a Go boundary.
- Do not implement Go/Fiber/Go Worker in this boundary.
- Do not claim a module is closed because a manifest guard or static guard exists.
- Treat `closed` module implementation status as unavailable unless code, tests, docs, legacy isolation/removal, freshness proof, operation barrier, force refresh and production evidence/defer status are all accounted for.
- If no pilot has enough local evidence for immediate implementation, close this boundary as `analysis-closed`, queue the smallest missing evidence collection boundary, and continue.

## Expected Output

- Analysis file with:
  - selected pilot candidate and rejected candidates
  - current query/write/refresh/repository/worker/front-end/API entry points
  - IO contract gaps
  - freshness/force-refresh/operation-barrier gaps
  - legacy contamination risks
  - seven-category test plan
  - exact first implementation slice
  - state-machine impact and transition
- Updated queue where the next pending item is an implementation boundary, not Go admission.
- Updated state/journal/next prompt.
- Docs verification and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one narrow verified planning/gap-audit slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
