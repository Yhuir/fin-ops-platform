# Next Prompt

Continue the autonomous modular IO refactor after the `workbench-relations:batch-accounting-pair-restore-service-delegation` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `workbench-relations:batch-accounting-pair-restore-service-delegation`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `workbench_relation` remains `implementation-gap-open`.
- Repository port extraction, derived lifecycle executor extraction, transaction persist repository owner split, command repository snapshot adapter extraction, non-transactional pair relation persist service extraction, pair relation rollback restore service extraction, exception rollback restore service extraction and batch-accounting restore service delegation are locally complete.
- Go hot-path candidates remain blocked by prerequisites.

## Next Boundary

`workbench-relations:post-batch-restore-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Perform planning-state preflight by reading `.planning/ROADMAP.md`, `.planning/refactors/README.md`, the modular IO requirements/state/roadmap/gates/runbook/stop-gates/Go carve-out docs, and all files in `.planning/refactors/modular-io-boundaries/autonomous/`.
4. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-batch-accounting-pair-restore-service-delegation.md`
   - `.planning/refactors/modular-io-boundaries/analysis/workbench-relations-post-restore-local-implementation-closure-audit.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/state-machine.md`
   - `docs/modules/workbench-relations/tests.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - relevant downstream module docs for any remaining relation callback candidates identified by the audit.
5. Use CodeGraph/text search for remaining app-owned relation callbacks/helpers and direct `pair_relation_service` wiring in `server.py`, route owners and downstream services.
6. Update `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this file after verification.

## Boundary Scope

Target:

- Re-audit remaining local `workbench_relation` gaps after batch-accounting restore delegation.
- Decide whether the next boundary should be another narrow implementation slice, a production-evidence-defer accounting slice, or a blocked/deferred item.
- Do not claim module closure unless every local implementation requirement and documented closure criterion is proven.
- Do not start Go/Fiber/Go Worker admission unless no earlier modular IO/read model implementation-pending or implementation-gap-open boundary remains.

Audit should classify at least:

- WorkbenchWriteFacade relation callback wiring after completed persist/restore service extractions.
- Turnover primary/legacy fallback relation callbacks.
- No-OA application/service relation callbacks.
- Pending invoice relation callbacks.
- Historical ETC repair/link/migration relation callbacks.
- Remaining `server.py` relation dependency assembly versus behavior ownership.

Forbidden:

- Do not implement code changes in this audit slice unless a trivial no-code deletion is proven safe.
- Do not change business rules, API payloads, write semantics, dirty scope semantics, read model refresh semantics or production state.
- Do not implement Go/Fiber/Go Worker.

## Expected Output

- Analysis/accounting slice.
- Updated docs/state/queue/journal/next prompt.
- Targeted docs verification and `git diff --check`.
- Commit and push to `origin/dev` if verification passes.
- Continue to the next pending boundary if safe.

## Stop Condition

Complete one verified `workbench-relations:post-batch-restore-local-implementation-closure-audit` slice, update analysis/docs/state, commit and push to `origin/dev`, then continue to the next pending boundary unless a hard stop gate is hit.
