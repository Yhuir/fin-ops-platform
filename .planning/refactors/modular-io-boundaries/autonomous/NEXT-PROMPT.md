# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-detail-module-closure-audit-and-production-evidence-defer` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-module-closure-audit-and-production-evidence-defer`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_detail` is still the first read model implementation pilot and remains `implementation-gap-open`.
- The closure audit found that `bank_detail` cannot be marked `closed` or only `production-evidence-deferred` because local implementation gaps remain in:
  - `Application._latest_bank_detail_auto_category_suggestion(...)`
  - `Application._enqueue_bank_detail_read_model_refreshes(...)`
  - `Application._delete_bank_detail_redis_cache(...)`
  - `Application._bank_detail_available_month_scope_keys(...)`
  - `Application._derived_lifecycle_bank_detail_executor(...)`
  - `Application._bank_details_application_service(...)` callback injection
- Production DB/worker/App Status/high-row evidence remains deferred and must not require local `PGSQL_URL` or staging DB.
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-suggestion-provider-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight:
   - Read `.planning/ROADMAP.md`.
   - Read `.planning/refactors/README.md`.
   - Read `.planning/refactors/modular-io-boundaries/README.md`.
   - Read `.planning/refactors/modular-io-boundaries/00-REQUIREMENTS.md`.
   - Read `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`.
   - Read `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`.
   - Read `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`.
   - Read `.planning/refactors/modular-io-boundaries/08-AUTONOMOUS-RUNBOOK.md`.
   - Read `.planning/refactors/modular-io-boundaries/10-AUTONOMOUS-STOP-GATES.md`.
   - Read `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`.
   - Read `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`.
   - Read this file.
   - If these files disagree on current state, next boundary, status labels, module closure meaning or completion metric source, stop normal implementation and create another `planning:state-reconciliation-*` slice first.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-pilot-verification-and-template-revision.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-server-helper-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-category-side-effect-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-module-closure-audit-and-production-evidence-defer.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/state-machine.md`
   - `docs/modules/bank-details/tests.md`
   - `docs/modules/bank-details/implementation-notes.md`
5. Use CodeGraph before editing to inspect `Application._latest_bank_detail_auto_category_suggestion(...)`, its callers, and the `BankDetailsApplicationService` constructor/provider contract.
6. Execute only one narrow bank detail implementation boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Extract or quarantine the latest auto-category suggestion provider out of `Application`.
- Make the suggestion provider an explicit service/provider/port dependency rather than an app-level compat callback.
- Preserve existing category suggestion semantics:
  - normalize transaction id;
  - load the transaction from the import service;
  - serialize/shape the row with the transaction id;
  - build the auto-category input row using the existing bank details service behavior or an equivalent service-owned public method;
  - call `BankTransactionAutoCategoryService.suggest_for_rows(...)`;
  - return the suggestion for the target transaction id.
- Preserve API response shape, permissions, audit behavior and read model freshness behavior.
- Add/adjust static guard coverage so `Application._latest_bank_detail_auto_category_suggestion(...)` cannot return.

Forbidden:

- Do not perform broad `server.py` splitting.
- Do not migrate refresh/wakeup wrappers, available-month scope helper or derived lifecycle executor in this same slice unless the suggestion provider extraction cannot compile without a tiny wiring change.
- Do not change finance business rules, category matching semantics, permission checks, audit action names, API shape, read model freshness semantics or frontend behavior unless explicitly required and tested.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Runtime code changes scoped to the suggestion provider boundary.
- Tests proving the provider behavior and preventing the old Application callback from returning.
- Updated module docs/state/journal/next prompt.
- Targeted API/service/read model/permission tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `read-models:bank-detail-suggestion-provider-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit. Before selecting or committing each subsequent slice, reconcile `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and state-machine semantics again; if they disagree, complete another planning reconciliation slice first.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
