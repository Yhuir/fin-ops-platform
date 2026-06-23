# Next Prompt

Continue the autonomous modular IO refactor after the `bank_detail` server helper quarantine slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:bank-detail-server-helper-quarantine`
- Last status: `implementation-closed`
- Queue semantics are corrected: slice status is not module closure.
- First read model implementation pilot: `bank_detail`.
- Implemented for `bank_detail` so far:
  - repository port/query boundary
  - write/force-refresh response `read_model_scope_keys`
  - operation barrier `freshness_targets`
  - exact month barrier target tests
  - removal of unused `server.py` `_get_bank_detail_*_from_sql_read_model` compat helpers
  - removal of unused `server.py` bank detail scope/freshness/cache/payload helpers
  - static guard proving `BankDetailsApplicationService` owns those read/cache helpers and retained refresh wrapper remains gateway-backed
- Still open for `bank_detail`:
  - category mutation side-effect callback extraction/quarantine
  - suggestion callback classification or collaborator extraction
  - production worker/readiness evidence or explicit defer status
- Go hot-path candidates remain blocked by prerequisites until relevant IO contracts, legacy isolation, freshness proof, tests, performance evidence, shadow-run plan and rollback evidence exist.

## Next Boundary

`read-models:bank-detail-category-side-effect-port-extraction`

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
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/bank-details/README.md`
   - `docs/modules/bank-details/state-machine.md`
   - `docs/modules/bank-details/tests.md`
   - `docs/modules/runtime-workers/README.md`
   - `docs/modules/runtime-workers/state-machine.md`
5. Use CodeGraph first to inspect:
   - `Application._after_bank_category_confirmation_mutation`
   - `Application._latest_bank_detail_auto_category_suggestion`
   - `BankDetailsApplicationService._persist_category_mutation`
   - category mutation API tests and turnover/workbench fan-out tests
6. Execute only the category side-effect port boundary. Do not implement Go/Fiber/Go Worker.
7. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- `Application._after_bank_category_confirmation_mutation(...)`
- `Application._latest_bank_detail_auto_category_suggestion(...)`
- `Application._bank_details_application_service(...)` callback injection for category side effects
- `BankDetailsApplicationService._persist_category_mutation(...)`

Allowed outcomes:

- Extract a small explicit side-effect collaborator/port for bank detail category mutation side effects.
- Or quarantine the callback with owner/caller/forbidden-write/deletion-condition tests if extraction is too broad.
- Keep refresh enqueue behind `ReadModelRefreshGateway`.
- Keep audit semantics and response shape unchanged.

Forbidden:

- Do not move business validation back into `server.py`.
- Do not directly SQL write `job.outbox_events` or `job.read_model_dirty_scopes`.
- Do not change category rules, affected month semantics, turnover/workbench fan-out, audit action names, API shape or permissions.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- A small implementation or static guard for category side-effect boundary.
- Updated module docs/state/journal/next prompt.
- Targeted API/service/read model/operation barrier tests, docs verification, app check and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `bank_detail` category side-effect port/quarantine slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.

## Reporting Rule

Any progress report must separately show:

- Root page-analysis roadmap progress from `.planning/ROADMAP.md`.
- Modular IO phase roadmap progress from `04-IMPLEMENTATION-ROADMAP.md`.
- Modular IO autonomous queue progress from `autonomous/MODULE-QUEUE.md`.
- Module implementation closure progress, not just slice closure.

Do not report a single unqualified percentage for "the whole refactor plan".
