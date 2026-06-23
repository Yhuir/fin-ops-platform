# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:bank-detail-derived-lifecycle-executor-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-derived-lifecycle-executor-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_detail` is still the first read model implementation pilot and remains `implementation-gap-open` until the remaining service factory collaborator wiring is audited.
- Completed local bank detail pilot work now includes repository port extraction, freshness/operation-barrier response contracts, legacy SQL helper removal, server read/cache helper quarantine, category side-effect port extraction, suggestion provider port extraction, refresh producer port extraction, available-month scope provider extraction and derived lifecycle executor extraction.
- Remaining local question:
  - Is `Application._bank_details_application_service(...)` now acceptable dependency assembly/wiring, or does it still contain bank_detail implementation logic that needs another extraction?
- Production DB/worker/App Status/high-row evidence remains deferred and must not require local `PGSQL_URL` or staging DB.
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-service-factory-collaborator-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read the latest bank detail analysis files and bank-details module docs.
5. Use CodeGraph before editing to inspect `Application._bank_details_application_service(...)`, `BankDetailsApplicationService.__init__`, and all bank_detail provider/producer/port collaborators.
6. Execute only one narrow bank detail closure audit or implementation boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit whether `Application._bank_details_application_service(...)` is now only dependency assembly and fallback wiring.
- If it contains business/read-model/worker behavior, split a new implementation boundary before module closure.
- If it is acceptable wiring, record local implementation closure evidence and defer only production PostgreSQL/worker/App Status/high-row evidence.
- Preserve API response shape, permissions, audit behavior, operation-barrier targets and read model freshness behavior.

Forbidden:

- Do not perform broad `server.py` splitting.
- Do not change finance business rules, category matching semantics, permission checks, audit action names, API shape, read model freshness semantics or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Runtime code changes only if the audit finds a narrow required extraction.
- Updated module docs/state/journal/next prompt.
- Targeted guard/docs/app checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `read-models:bank-detail-service-factory-collaborator-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
