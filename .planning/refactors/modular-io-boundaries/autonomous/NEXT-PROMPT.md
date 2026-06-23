# Next Prompt

Continue the autonomous modular IO refactor after the `planning:semantic-queue-state-and-master-goal-refresh` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:semantic-queue-state-and-master-goal-refresh`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `bank_detail` current local implementation support slices are complete through the collaborator audit, but this is not full module closure.
- `bank_detail` full module closure is not claimed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- The remaining `Application._bank_details_application_service(...)` code has been audited as acceptable dependency assembly/wiring.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`read-models:next-pilot-selection-after-bank-detail`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-manifest-and-boundary-inventory.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-pilot-gap-audit-and-contract-selection.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-service-factory-collaborator-closure-audit.md`
   - `docs/app-architecture/runtime-and-ownership.md`
   - `docs/modules/README.md`
5. Select the next read model implementation pilot from current manifest/roadmap evidence. Do not select Go/Fiber/Go Worker.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Compare remaining read model candidates such as `workbench_relation`, `pending_invoice`, `oa_pending_payment`, `invoice_lifecycle`, `input_invoice_usage`, `output_invoice_collection`, `cost_statistics`, `tax_offset`, `turnover_ledger`, `search` and `no_oa_bank_batch`.
- Choose the next highest-value implementation pilot based on bug frequency, cross-page freshness risk, remaining legacy contamination, test coverage, scope size and implementation sequencing.
- Queue the first narrow implementation boundary for that pilot.
- Keep Go hot-path admission blocked until prerequisite modular IO implementation evidence exists.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not touch production state.
- Do not perform runtime code changes unless a tiny static verification helper is required for the selection artifact.

## Expected Output

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/`.
- Updated queue/state/journal/next prompt.
- Docs verification and diff checks.
- Commit and push to `origin/dev` if verification passes.

## Stop Condition

Complete one verified `read-models:next-pilot-selection-after-bank-detail` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending implementation boundary unless a hard stop gate is hit.
