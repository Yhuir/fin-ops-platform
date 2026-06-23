# Next Prompt

Continue the autonomous modular IO refactor after the `batch-accounting:legacy-route-implementation` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `batch-accounting:legacy-route-implementation`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- The completed batch-accounting slice extracted read-only `GET /api/batch-accounting` query normalization and list error mapping into `BatchAccountingApiRoutes`; `BatchAccountingService.build_payload(..., use_sql_read_model=True)` remains the read contract owner.
- Submit/withdraw mutation route mapping and write-after side-effect boundaries still remain in `server.py`.
- Broader `server.py` shared-boundary cleanup remains `implementation-gap-open`.
- Broader `batch-accounting` module closure remains `implementation-gap-open`.
- `bank_detail` remains the first read model implementation pilot and is still not module-closed.
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`batch-accounting:submit-withdraw-route-side-effect-port`

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
   - `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-legacy-route-contract.md`
   - `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-get-route-owner-extraction.md`
   - `docs/app-architecture/runtime-and-ownership.md`
   - `docs/modules/README.md`
   - `docs/modules/batch-accounting/README.md`
   - `docs/modules/batch-accounting/state-machine.md`
   - `docs/modules/batch-accounting/tests.md`
5. Use CodeGraph first to inspect the selected batch-accounting submit/withdraw route handlers, service owner, callers, callees and impact.
6. Execute only one narrow batch-accounting mutation route/service implementation boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Convert one batch-accounting submit/withdraw route side-effect boundary from `server.py` inline mapping into an explicit route owner or side-effect port.
- Prefer the smallest mutation route with clear existing tests.
- Keep `server.py` thin: HTTP parsing, session/auth resolution, dependency wiring and response mapping only.

Allowed outcomes:

- Move a narrow mutation route body into an existing route/service boundary.
- Or quarantine a legacy batch-accounting handler with owner/caller/forbidden-write/deletion-condition tests if extraction is too broad.
- Preserve API response shape, permissions, audit and read model behavior.
- Keep write-after lifecycle/read model refresh/barrier behavior behind existing service/command boundaries.

Forbidden:

- Do not perform broad line-count file splitting.
- Do not migrate unrelated modules in the same slice.
- Do not change finance business rules, permissions, audit action names, API shape, read model freshness semantics or frontend behavior unless explicitly required and tested.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- One small implementation or static quarantine guard for the selected batch-accounting mutation boundary.
- Updated module docs/state/journal/next prompt.
- Targeted API/service/read model/permission tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified batch-accounting mutation route implementation/quarantine slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit. Before selecting or committing each subsequent slice, reconcile `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and state-machine semantics again; if they disagree, complete another planning reconciliation slice first.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
