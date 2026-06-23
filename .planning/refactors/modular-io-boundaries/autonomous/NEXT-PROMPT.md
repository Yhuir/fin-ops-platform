# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:turnover-workbench-pair-port-required-command-constructor` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:turnover-workbench-pair-port-required-command-constructor`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- `TurnoverLedgerWorkbenchPairPort` no longer accepts or stores broad `pair_relation_service`.
- Turnover Workbench pair writes remain command-service backed and relation reads remain facade-backed.
- `TurnoverLedgerLocalClosureConnection` still retains pair service for local rollback snapshot behavior and is not closed by the previous slice.
- Workbench matching orchestrator/engine still read broad `WorkbenchPairRelationService`; this is the next audit boundary.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:workbench-matching-pair-service-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-turnover-workbench-pair-port-required-command-constructor.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
5. Inspect:
   - `backend/src/fin_ops_platform/services/workbench_matching_orchestrator.py`
   - `backend/src/fin_ops_platform/services/workbench_reconciliation_engine.py`
   - `backend/src/fin_ops_platform/app/server.py`
   - relevant Workbench matching/orchestrator tests and boundary guards
6. Use CodeGraph/text search for `WorkbenchMatchingOrchestrator`, `WorkbenchReconciliationEngine`, `pair_relation_service`, `_pair_relation_service`, `list_active_relations`, and `active_relations_for_row_ids`.
7. Produce an analysis/accounting file under `.planning/refactors/modular-io-boundaries/analysis/`.
8. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Audit Workbench matching orchestrator and reconciliation engine broad pair service reads.
- Classify whether these reads are canonical fact reads, read-model distribution reads, command-service precondition reads, matching-only candidate context, or local in-memory compatibility reads.
- Decide the next smallest safe boundary.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not change matching, grouping, candidate, dirty scope, read model refresh, relation write, or API response behavior in this audit slice.
- Do not declare `workbench_relation` module closed.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:workbench-matching-pair-service-boundary-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
