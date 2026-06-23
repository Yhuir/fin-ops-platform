# Next Prompt

Continue the autonomous modular IO refactor after the `batch-accounting:module-closure-audit-and-production-evidence-defer` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `batch-accounting:module-closure-audit-and-production-evidence-defer`
- Last status: `production-evidence-deferred`
- Queue semantics remain corrected: slice status is not module closure.
- The completed batch-accounting slice recorded local IO/route/service/legacy/read-model freshness/operation-barrier/test/docs closure evidence and deferred real PostgreSQL/worker/App Status/history/high-row production evidence.
- `server.py` still owns mutation session, JSON body parsing and response mapping for batch-accounting routes.
- Broader `server.py` shared-boundary cleanup remains `implementation-gap-open`.
- `batch-accounting` remains not full-closed because production evidence is deferred, not because another local implementation slice is currently known.
- `bank_detail` remains the first read model implementation pilot and is still not module-closed.
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-module-closure-audit-and-production-evidence-defer`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-pilot-verification-and-template-revision.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-server-helper-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-category-side-effect-port-extraction.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/state-machine.md`
   - `docs/modules/bank-details/tests.md`
   - `docs/modules/bank-details/implementation-notes.md`
   - `docs/app-architecture/runtime-and-ownership.md`
   - `docs/modules/README.md`
   - `docs/modules/batch-accounting/README.md`
   - `docs/modules/batch-accounting/state-machine.md`
   - `docs/modules/batch-accounting/tests.md`
5. Use CodeGraph and rg to audit remaining bank_detail read model/application/server helper/callback/legacy references and module docs.
6. Execute only one narrow bank_detail closure audit/evidence-defer boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Decide whether bank_detail can move toward `closed`, `production-evidence-deferred`, or must remain `implementation-gap-open`.
- Audit IO contract, route owner, application service owner, canonical fact owner, read model/freshness, force refresh, operation barrier, permissions, audit, tests, docs and legacy removal.
- Do not require local `PGSQL_URL` or staging DB; if only real production worker/DB evidence is missing, record `production-evidence-deferred`.
- Keep `server.py` thin: HTTP parsing, session/auth resolution, dependency wiring and response mapping only.

Allowed outcomes:

- Update module closure accounting if evidence supports it.
- Or keep module open with exact remaining implementation gaps.
- Preserve API response shape, permissions, audit and read model behavior.

Forbidden:

- Do not perform broad line-count file splitting.
- Do not migrate unrelated modules in the same slice.
- Do not change finance business rules, permissions, audit action names, API shape, read model freshness semantics or frontend behavior unless explicitly required and tested.
- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- One closure audit analysis file and any needed docs/state accounting updates.
- Updated module docs/state/journal/next prompt.
- Targeted API/service/read model/permission tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified bank_detail closure audit/evidence-defer slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit. Before selecting or committing each subsequent slice, reconcile `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and state-machine semantics again; if they disagree, complete another planning reconciliation slice first.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
