# Next Prompt

Continue the autonomous modular IO refactor after the `bank_detail` freshness/force-refresh/operation-barrier slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-refresh-freshness-operation-barrier`
- Last status: `implementation-closed`
- Queue semantics are corrected: prior guard/analysis slices are slice-complete only and do not mean module implementation closure.
- First read model implementation pilot: `bank_detail`.
- Implemented for `bank_detail` so far:
  - repository port/query boundary
  - write/force-refresh response `read_model_scope_keys`
  - operation barrier `freshness_targets`
  - exact month barrier target tests
- Still open for `bank_detail`:
  - legacy contamination removal/quarantine
  - pilot verification/template revision
  - production worker/readiness evidence or explicit defer status
- Go hot-path candidates are blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-legacy-contamination-removal`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-refresh-freshness-operation-barrier.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/runtime-workers/README.md`
   - `docs/modules/runtime-workers/state-machine.md`
5. Use CodeGraph first to locate current `bank_detail` legacy helpers, callers, callees, routes and tests.
6. Implement only a narrow `bank_detail` legacy contamination removal/quarantine slice.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Selection Rules

- The pilot is already selected: `bank_detail`.
- Repository port/query and freshness/barrier response contracts are implemented, but module closure remains open.
- Do not choose a Go boundary.
- Do not implement Go/Fiber/Go Worker in this boundary.
- Do not claim a module is closed because a manifest guard, static guard, repository port, or freshness/barrier response exists.
- Treat `closed` module implementation status as unavailable unless code, tests, docs, legacy isolation/removal, freshness proof, operation barrier, force refresh and production evidence/defer status are all accounted for.
- If legacy removal exposes a broader scope than one safe slice, split the boundary and execute the first smaller removal/quarantine slice.

## Expected Output

- Implementation changes removing or quarantining selected `bank_detail` legacy helper/path only.
- Tests proving new BankDetails query/write/refresh paths do not call removed/quarantined legacy internals.
- Regression evidence preserving:
  - repository port/query boundary
  - force refresh gateway/scope policy usage
  - exact month operation barrier targets
  - API response shape
- Updated analysis/state/journal/next prompt.
- Docs verification and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one narrow verified `bank_detail` legacy contamination removal/quarantine slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
