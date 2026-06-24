# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:no-oa-bank-batch-post-full-state-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `no_oa_bank_batch` local implementation support is accounted for after repository port, refresh persistence port, derived lifecycle executor, mutation persistence fallback quarantine, full-state snapshot quarantine and source-version helper cleanup.
- `no_oa_bank_batch` is not globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- Remaining non-Go read model candidates include `search` and `bank_account_balance`.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:next-pilot-selection-after-no-oa-bank-batch`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-post-full-state-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-full-state-snapshot-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-no-oa-bank-batch-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-search-and-no-oa-bank-batch-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-and-bank-account-balance-contract.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - relevant module docs for `search` and `bank-account-balance` if present.
6. Use CodeGraph and `rg` to inspect current search and bank account balance code surfaces before selecting the next pilot.

## Boundary Scope

Target:

- Compare remaining non-Go read model candidates, especially `search` and `bank_account_balance`.
- Select the next pilot based on stale-read risk, cross-page fan-out impact, available repository/refresh boundaries, legacy contamination risk, testability and Go admission prerequisites.
- Insert the first concrete pending boundary for the selected module before Go candidates.
- Do not implement the selected module in this selection slice unless the queue/state files are inconsistent and require a planning repair.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not mark any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`
- If any Python import or manifest file changes, run `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`.

## Stop Condition

Complete one verified next-pilot selection slice, commit and push to `origin/dev`, then continue to the selected module's first implementation/audit boundary unless a hard stop gate is hit.
