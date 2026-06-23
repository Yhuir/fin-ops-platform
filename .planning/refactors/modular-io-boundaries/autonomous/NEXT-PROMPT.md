# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-detail-refresh-producer-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-refresh-producer-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_detail` is still the first read model implementation pilot and remains `implementation-gap-open`.
- Completed local bank detail pilot work now includes repository port extraction, freshness/operation-barrier response contracts, legacy SQL helper removal, server read/cache helper quarantine, category side-effect port extraction, suggestion provider port extraction and refresh producer port extraction.
- Remaining local implementation gaps include:
  - `Application._bank_detail_available_month_scope_keys(...)`
  - `Application._derived_lifecycle_bank_detail_executor(...)`
  - `Application._bank_details_application_service(...)` retained collaborator injection
- Production DB/worker/App Status/high-row evidence remains deferred and must not require local `PGSQL_URL` or staging DB.
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-available-month-scope-provider-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read the latest bank detail analysis files, especially:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-module-closure-audit-and-production-evidence-defer.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-suggestion-provider-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-refresh-producer-port-extraction.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/state-machine.md`
   - `docs/modules/bank-details/tests.md`
   - `docs/modules/bank-details/implementation-notes.md`
5. Use CodeGraph before editing to inspect `Application._bank_detail_available_month_scope_keys(...)`, its callers and the `BankDetailsApplicationService` `available_month_scope_keys_provider` injection contract.
6. Execute only one narrow bank detail implementation boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Extract available-month scope calculation out of `Application`.
- Preserve current all-scope fan-out semantics: use import transactions, inspect known transaction date fields, return sorted `YYYY-MM` months, and fall back to `["all"]`.
- Preserve API response shape, permissions, audit behavior, operation-barrier targets and read model freshness behavior.
- Add/adjust tests and guards so the old app-level available-month scope helper cannot return.

Forbidden:

- Do not migrate the derived lifecycle executor in this same slice unless the scope provider extraction cannot compile without a tiny wiring change.
- Do not perform broad `server.py` splitting.
- Do not change finance business rules, category matching semantics, permission checks, audit action names, API shape, read model freshness semantics or frontend behavior unless explicitly required and tested.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Runtime code changes scoped to available-month scope provider extraction.
- Tests proving scope calculation behavior and preventing the old app-level helper from returning.
- Updated module docs/state/journal/next prompt.
- Targeted API/service/read model/permission tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `read-models:bank-detail-available-month-scope-provider-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
