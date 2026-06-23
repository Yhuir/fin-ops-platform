# Next Prompt

Continue the autonomous modular IO refactor after the `batch-accounting:submit-withdraw-route-side-effect-port` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `batch-accounting:submit-withdraw-route-side-effect-port`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- The completed batch-accounting slice extracted submit/withdraw mutation DTO/service/error mapping and write-after scope/lifecycle/read-model persist orchestration into `BatchAccountingApiRoutes` with explicit callbacks.
- `server.py` still owns mutation session, JSON body parsing and response mapping for batch-accounting routes.
- `_repair_batch_accounting_relation_case_ids` remains an explicit compat/repair helper and still needs owner/caller/deletion-condition quarantine or removal evidence.
- Broader `server.py` shared-boundary cleanup remains `implementation-gap-open`.
- Broader `batch-accounting` module closure remains `implementation-gap-open`.
- `bank_detail` remains the first read model implementation pilot and is still not module-closed.
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`batch-accounting:repair-compat-quarantine`

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
   - `.planning/refactors/modular-io-boundaries/analysis/batch-accounting-submit-withdraw-route-side-effect-port.md`
   - `docs/app-architecture/runtime-and-ownership.md`
   - `docs/modules/README.md`
   - `docs/modules/batch-accounting/README.md`
   - `docs/modules/batch-accounting/state-machine.md`
   - `docs/modules/batch-accounting/tests.md`
5. Use CodeGraph first to inspect `_repair_batch_accounting_relation_case_ids`, `BatchAccountingService.repair_legacy_case_id_collisions`, callers, callees and impact.
6. Execute only one narrow batch-accounting repair compat quarantine/removal boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Classify `_repair_batch_accounting_relation_case_ids` as removed, quarantined, compat-only or blocked-by-human-gate.
- Prefer removal if CodeGraph and tests prove it is unused.
- If retained, document owner, caller list, deletion condition, forbidden write list and regression tests.
- Keep `server.py` thin: HTTP parsing, session/auth resolution, dependency wiring and response mapping only.

Allowed outcomes:

- Remove the repair helper if unused.
- Or quarantine the repair helper with owner/caller/forbidden-write/deletion-condition tests if removal is too broad.
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
- One small implementation or static quarantine guard for the selected batch-accounting repair boundary.
- Updated module docs/state/journal/next prompt.
- Targeted API/service/read model/permission tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified batch-accounting repair quarantine/removal slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit. Before selecting or committing each subsequent slice, reconcile `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and state-machine semantics again; if they disagree, complete another planning reconciliation slice first.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
