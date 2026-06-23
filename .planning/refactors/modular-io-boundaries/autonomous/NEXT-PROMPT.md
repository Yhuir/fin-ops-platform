# Next Prompt

Continue the autonomous modular IO refactor after the queue semantics and master goal prompt revision slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:queue-semantics-and-master-goal-prompt-revision`
- Last status: `planning-closed`
- Queue semantics are corrected: slice status is not module closure.
- First read model implementation pilot: `bank_detail`.
- Implemented for `bank_detail` so far:
  - repository port/query boundary
  - write/force-refresh response `read_model_scope_keys`
  - operation barrier `freshness_targets`
  - exact month barrier target tests
  - removal of unused `server.py` `_get_bank_detail_*_from_sql_read_model` compat helpers
  - removal of unused `server.py` bank detail scope/freshness/cache/payload helpers
  - explicit `BankDetailCategoryMutationSideEffectPort` for category write side effects
  - static guard proving removed `Application._after_bank_category_confirmation_mutation(...)` cannot return
- Still open for `bank_detail`:
  - production worker/readiness evidence remains deferred because there is no local `PGSQL_URL` or staging DB
  - `Application._latest_bank_detail_auto_category_suggestion(...)` is classified as a compat-only read callback, not extracted
  - shared gateway/scope support wrappers remain classified, not globally extracted
- `server-py:legacy-handler-extraction-implementation` is the next executable shared-boundary implementation slice. It is not evidence that `bank_detail` is fully module-closed.
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`server-py:legacy-handler-extraction-implementation`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-category-side-effect-port-extraction.md`
   - `docs/app-architecture/runtime-and-ownership.md`
   - `docs/modules/README.md`
   - target module docs for the selected `server.py` legacy handler area before editing
5. Use CodeGraph first to inspect the selected legacy handler, its route owner, callers, callees and impact.
6. Execute only one narrow server.py handler extraction/quarantine boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Select the first high-value legacy handler still owned by `server.py` whose extraction is small enough for one safe slice.
- Prefer an existing `routes_*.py` / service owner from the route owner inventory.
- Keep `server.py` thin: HTTP parsing, session/auth resolution, route/service construction and response mapping only.

Allowed outcomes:

- Move a narrow legacy handler body into an existing route/service boundary.
- Or quarantine a legacy handler with owner/caller/forbidden-write/deletion-condition tests if extraction is too broad.
- Preserve API response shape, permissions, audit and read model behavior.

Forbidden:

- Do not perform broad line-count file splitting.
- Do not migrate unrelated modules in the same slice.
- Do not change finance business rules, permissions, audit action names, API shape, read model freshness semantics or frontend behavior unless explicitly required and tested.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- One small implementation or static guard for the selected server.py legacy handler boundary.
- Updated module docs/state/journal/next prompt.
- Targeted API/service/read model/permission tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified server.py legacy handler extraction/quarantine slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit. Before selecting or committing each subsequent slice, reconcile `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and state-machine semantics again; if they disagree, complete another planning reconciliation slice first.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
