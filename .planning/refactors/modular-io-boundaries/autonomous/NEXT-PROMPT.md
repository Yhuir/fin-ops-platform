# Next Prompt

Continue the autonomous modular IO refactor after the `bank_detail` legacy contamination removal slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-legacy-contamination-removal`
- Last status: `implementation-closed`
- Queue semantics are corrected: prior guard/analysis slices are slice-complete only and do not mean module implementation closure.
- First read model implementation pilot: `bank_detail`.
- Implemented for `bank_detail` so far:
  - repository port/query boundary
  - write/force-refresh response `read_model_scope_keys`
  - operation barrier `freshness_targets`
  - exact month barrier target tests
  - removal of unused `server.py` `_get_bank_detail_*_from_sql_read_model` compat helpers
- Still open for `bank_detail`:
  - pilot verification/template revision
  - production worker/readiness evidence or explicit defer status
  - classification of any remaining `server.py` bank detail scope/cache/refresh compat helpers
- Go hot-path candidates are blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-pilot-verification-and-template-revision`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-legacy-contamination-removal.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/state-machine.md`
   - `docs/modules/bank-details/tests.md`
   - `docs/modules/runtime-workers/README.md`
   - `docs/modules/runtime-workers/state-machine.md`
5. Use CodeGraph first to inspect remaining `bank_detail` query/refresh/cache/helper ownership and test coverage.
6. Execute only the pilot verification/template revision boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Selection Rules

- The pilot remains `bank_detail`.
- Repository port/query, freshness/barrier response contracts and first legacy SQL helper removal are implemented.
- Do not choose a Go boundary.
- Do not implement Go/Fiber/Go Worker in this boundary.
- Do not claim full module closure unless the completion definition is actually satisfied or explicitly records production evidence deferred.
- If verification reveals remaining legacy paths that are too large to handle in one slice, split the queue before proceeding.

## Expected Output

- A pilot verification analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Verification of the bank_detail pilot against IO contract, legacy removal/quarantine, read model freshness, force refresh, operation barrier, permissions/audit, tests, docs and environment evidence/defer status.
- Template/runbook updates only if pilot evidence shows a template gap.
- Updated docs/state/journal/next prompt.
- Targeted tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `bank_detail` pilot verification/template revision slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
