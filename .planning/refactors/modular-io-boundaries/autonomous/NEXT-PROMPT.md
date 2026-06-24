# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:cost-statistics-post-full-state-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:cost-statistics-post-full-state-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `cost_statistics` local implementation support is accounted for after repository port, freshness/barrier audit, derived lifecycle executor extraction and full-state snapshot quarantine.
- `cost_statistics` is not globally closed; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- Remaining non-Go read model candidates include `turnover_ledger`, `no_oa_bank_batch`, `search` and `bank_account_balance`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-cost-statistics`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-post-full-state-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-full-state-read-model-snapshot-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-tax-offset.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/cost-statistics/implementation-notes.md`
   - `docs/modules/cost-statistics/tests.md`
   - module docs for any candidate module selected by evidence.
6. Use CodeGraph for structural lookup before selecting implementation work.

## Boundary Scope

Target:

- Select the next non-Go read model modular IO pilot after `cost_statistics`.
- Compare remaining candidates by user-visible stale-read risk, cross-page consistency risk, current implementation gap clarity, narrow first-slice feasibility, existing tests, and Go-admission prerequisites.
- Do not select Go/Fiber/Go Worker while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
- If the next module is clear, insert its first narrow implementation boundary before Go candidates and set it as the next prompt.
- If candidate evidence is insufficient, insert a smaller candidate-audit boundary before selecting implementation.
- Update planning state, queue, journal, next prompt, master prompt and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not start broad global refactors.
- Do not change business behavior, API shape, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning or frontend behavior.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified next-pilot selection slice, commit and push to `origin/dev`, then continue to the selected next safe boundary unless a hard stop gate is hit.
