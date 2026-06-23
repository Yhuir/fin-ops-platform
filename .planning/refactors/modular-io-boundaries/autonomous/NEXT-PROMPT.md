# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:turnover-workbench-pair-port-unused-persist-callback-removal` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:turnover-workbench-pair-port-unused-persist-callback-removal`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Turnover pair port no longer carries unused persist callback wiring.
- `TurnoverLedgerWorkbenchPairPort.pair_relation_service` remains read-only compat fallback.
- Pending invoice, no-OA, ETC and WorkbenchWriteFacade relation dependencies still need focused classification.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:pending-invoice-pair-service-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-workbench-pair-port-unused-persist-callback-removal.md`
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
5. Use CodeGraph/text search for `PendingInvoiceQueryService`, `PendingInvoiceApplicationService`, `pair_relation_service`, `relation_facade`, `relation_command_service`, and write/read callers.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit pending invoice query/application pair service dependencies.
- Decide whether pair service dependency can be removed, should become read-facade/command-service-only, or must remain `compat-only`.
- Classify query and application service separately.
- Produce an analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.

Forbidden:

- Do not migrate pending invoice behavior in this audit slice unless a trivial no-code deletion is proven safe and queue is updated.
- Do not change pending invoice attach/manual invoice business rules, API payloads, dirty scope semantics, read model refresh semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:pending-invoice-pair-service-boundary-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
