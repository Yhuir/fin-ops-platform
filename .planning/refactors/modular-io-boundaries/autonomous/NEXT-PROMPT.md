# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-account-balance-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-account-balance-local-implementation-closure-audit`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_account_balance` local implementation support is accounted for after repository port, refresh producer, derived lifecycle executor, all-only scope policy, operation barrier regressions and Bank Detail fallback removal.
- `bank_account_balance` is not globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- No Go/Fiber/Go Worker candidate has passed admission.
- Go implementation remains blocked until performance evidence, shadow-run plan, rollback gates and candidate-specific IO contracts are reconciled.

## Next Boundary

`go-hot-path:performance-baseline-and-admission-reconciliation`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-local-implementation-closure-audit.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/bank-account-balance/README.md`
   - `docs/operations/runtime-worker-governance.md`
   - relevant performance/test tooling under `scripts/`, `backend/src/fin_ops_platform/tools/`, and existing tests.

## Boundary Scope

Target:

- Reconcile whether all prior non-Go read model implementation-pending queue items are locally accounted for or still block Go admission.
- Identify what performance evidence already exists locally, what can be collected without `PGSQL_URL`/staging, and what must stay `production-evidence-deferred`.
- Decide whether any queued Go candidate can move from `blocked-by-prerequisite` to a bounded admission review.
- If no candidate passes gates, mark the candidate(s) `go-candidate-deferred` or keep blocked with concrete missing evidence.
- Do not implement Go, Go Fiber or Go Worker in this slice.
- Do not change Python runtime behavior.

Expected verification:

- `bash scripts/verify.sh docs`
- `git diff --check`
- Any targeted tooling/docs/tests required by the admission reconciliation.

## Stop Condition

Complete one verified Go admission/performance-baseline reconciliation slice, update state-machine accounting, commit and push to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
