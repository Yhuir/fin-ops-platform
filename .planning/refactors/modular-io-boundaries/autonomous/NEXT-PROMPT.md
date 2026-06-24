# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-full-state-read-model-snapshot-quarantine` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-full-state-read-model-snapshot-quarantine`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- Repository port, freshness/barrier, worker rebuild executor, derived lifecycle executor, cache warmup executor and full-state snapshot quarantine slices are implemented.
- Broad `Application._persist_state(...)` no longer serializes `tax_offset_read_models`.
- Explicit tax offset read model persistence through runtime/executor boundaries remains available through `_persist_tax_offset_read_models_best_effort(...)`.
- `TaxOffsetReadModelService.from_snapshot(...)` bootstrap remains compatibility support for local/Mongo snapshots.
- `tax_offset` is still `implementation-gap-open` until post-quarantine local closure audit proves all local implementation support is accounted for.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-post-full-state-local-implementation-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target planning evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-worker-rebuild-executor-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-derived-lifecycle-executor-boundary-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-cache-warmup-executor-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-final-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-full-state-read-model-snapshot-quarantine.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/tax-offset/implementation-notes.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
6. Use CodeGraph for structural lookup before any implementation decision.

## Boundary Scope

Target:

- Re-audit `tax_offset` after full-state snapshot quarantine.
- Prove whether all local implementation support is accounted for across repository port, fresh gate, force refresh, operation barrier, worker rebuild, derived lifecycle, optional cache warmup, broad full-state persistence quarantine, legacy path removal/quarantine, permissions, audit, tests and docs.
- If no local implementation gap remains, mark only local implementation support as accounted for and move the module to `production-evidence-deferred` with explicit missing real PostgreSQL/worker/App Status/high-row/browser evidence.
- If a local implementation gap remains, do not defer. Insert the next narrow implementation boundary before Go candidates and keep `tax_offset` implementation-gap-open.
- Produce/update an analysis file documenting evidence, gaps/defer decision, state-machine impact, seven-category test applicability, verification and next boundary.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim `tax_offset` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change tax business semantics, amount rules, certification rules, plan save API shape, permissions, audit meaning, worker event names, queue schema, Redis key/envelope contract or frontend behavior.

Expected verification:

- Targeted static guards for any audited local closure claim.
- Relevant tax offset executor/API/runtime tests when evidence depends on executable behavior.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified tax offset post-quarantine local closure audit slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
