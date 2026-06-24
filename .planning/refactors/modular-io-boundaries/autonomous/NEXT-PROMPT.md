# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:invoice-lifecycle-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:invoice-lifecycle-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `invoice_lifecycle` local implementation support is accounted for after repository port, freshness/barrier and derived lifecycle executor slices.
- `invoice_lifecycle` is not globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-invoice-lifecycle`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target planning evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-derived-lifecycle-executor-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/06-PILOT-SELECTION.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
6. Use CodeGraph for structural lookup before any implementation edits.

## Boundary Scope

Target:

- Select the next non-Go modular IO/read model pilot from remaining implementation-gap-open modules.
- Do not select Go hot-path admission while modular IO/read model implementation-pending or implementation-gap-open work remains.
- Compare remaining candidates using stale-read/cross-page risk, user-visible bug frequency, IO boundary readiness, legacy contamination risk, testability without local `PGSQL_URL`, and scope size.
- Produce/update an analysis file documenting the candidate comparison and selected next boundary.
- Insert the selected next implementation boundary before blocked Go candidates in `MODULE-QUEUE.md`.
- Update `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests as applicable.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`
- Runtime tests are not required for selection-only analysis unless runtime code changes.

## Stop Condition

Complete one verified next-pilot selection slice, commit and push to `origin/dev`, then continue to the selected next implementation boundary unless a hard stop gate is hit.
