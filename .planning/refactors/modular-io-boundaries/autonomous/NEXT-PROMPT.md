# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-detail-suggestion-provider-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-suggestion-provider-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_detail` is still the first read model implementation pilot and remains `implementation-gap-open`.
- Completed local bank detail pilot work now includes repository port extraction, freshness/operation-barrier response contracts, legacy SQL helper removal, server read/cache helper quarantine, category side-effect port extraction and suggestion provider port extraction.
- Remaining local implementation gaps include:
  - `Application._enqueue_bank_detail_read_model_refreshes(...)`
  - `Application._delete_bank_detail_redis_cache(...)`
  - `Application._bank_detail_available_month_scope_keys(...)`
  - `Application._derived_lifecycle_bank_detail_executor(...)`
  - `Application._bank_details_application_service(...)` retained collaborator injection
- Production DB/worker/App Status/high-row evidence remains deferred and must not require local `PGSQL_URL` or staging DB.
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-refresh-producer-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read the latest bank detail analysis files, especially:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-category-side-effect-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-module-closure-audit-and-production-evidence-defer.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-suggestion-provider-port-extraction.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/state-machine.md`
   - `docs/modules/bank-details/tests.md`
   - `docs/modules/bank-details/implementation-notes.md`
5. Use CodeGraph before editing to inspect `Application._enqueue_bank_detail_read_model_refreshes(...)`, `Application._delete_bank_detail_redis_cache(...)`, their callers and the `BankDetailsApplicationService` injection contract.
6. Execute only one narrow bank detail implementation boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Extract or narrow the bank detail refresh/wakeup producer boundary.
- Keep refresh enqueue behind `ReadModelRefreshGateway` / scope policy.
- Preserve Redis wakeup semantics as optional transport/wakeup, not read model freshness fact source.
- Preserve API response shape, permissions, audit behavior, operation-barrier targets and read model freshness behavior.
- Add/adjust guard coverage so new code cannot directly SQL-write `job.outbox_events` or `job.read_model_dirty_scopes` and so old app-level refresh/wakeup ownership is either removed or explicitly classified.

Forbidden:

- Do not migrate available-month scope helper or derived lifecycle executor in this same slice unless the refresh producer extraction cannot compile without a tiny wiring change.
- Do not perform broad `server.py` splitting.
- Do not change finance business rules, category matching semantics, permission checks, audit action names, API shape, read model freshness semantics or frontend behavior unless explicitly required and tested.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Runtime code changes scoped to the refresh producer/wakeup boundary.
- Tests proving refresh enqueue still uses the gateway and no direct queue SQL is introduced.
- Updated module docs/state/journal/next prompt.
- Targeted API/service/read model/permission tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `read-models:bank-detail-refresh-producer-port-extraction` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
