# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:pending-invoice-pair-service-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:pending-invoice-pair-service-boundary-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Pending invoice query/application services still receive unused `pair_relation_service` constructor injection.
- Pending invoice relation reads use `relation_facade`.
- Pending invoice relation writes use `relation_command_service`.
- No-OA, ETC and WorkbenchWriteFacade relation dependencies still need focused classification.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:pending-invoice-unused-pair-service-removal`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-pending-invoice-pair-service-boundary-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `docs/modules/pending-invoices/README.md`
   - `docs/modules/pending-invoices/state-machine.md`
   - `docs/modules/pending-invoices/tests.md`
   - `backend/src/fin_ops_platform/services/pending_invoice_service.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - relevant pending-invoice relation tests.
5. Use CodeGraph/text search for `PendingInvoiceQueryService`, `PendingInvoiceApplicationService`, `pair_relation_service`, `_pair_relation_service`, `relation_facade`, `relation_command_service`, and write/read callers.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Remove unused `pair_relation_service` parameter and `_pair_relation_service` field from `PendingInvoiceQueryService`.
- Remove unused `pair_relation_service` parameter and `_pair_relation_service` field from `PendingInvoiceApplicationService`.
- Remove pending invoice `pair_relation_service=...` wiring in `server.py`.
- Update pending invoice tests/fixtures to stop passing pair services.
- Strengthen runtime boundary guards so pending invoice services cannot re-accept or import `WorkbenchPairRelationService`.
- Remove stale pending invoice allowed-context entries for direct pair relation reads if they are no longer needed.
- Produce an implementation analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not change pending invoice attach/manual invoice business rules, API payloads, dirty scope semantics, read model refresh semantics or production state.
- Do not change `relation_facade` or `relation_command_service` semantics.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:pending-invoice-unused-pair-service-removal` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
