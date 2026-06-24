# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-final-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-final-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- Repository port, freshness/barrier, worker rebuild executor, derived lifecycle executor and cache warmup executor slices are implemented.
- Final local closure audit found a remaining local implementation gap: broad `Application._persist_state(...)` still serializes `tax_offset_read_models` into the legacy full-state snapshot path.
- Explicit tax offset read model persistence through runtime/executor boundaries uses `_persist_tax_offset_read_models_best_effort(...)` and must remain available.
- `TaxOffsetReadModelService.from_snapshot(...)` bootstrap is currently compatibility support for local/Mongo runtime, but broad `_persist_state(...)` must not keep writing read model snapshots as a second writer.
- `tax_offset` is still `implementation-gap-open`; it cannot move to `production-evidence-deferred` until this full-state snapshot write path is removed or quarantined.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-full-state-read-model-snapshot-quarantine`

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
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/tax-offset/implementation-notes.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
6. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Remove or quarantine broad `Application._persist_state(...)` writes of `tax_offset_read_models`.
- Preserve explicit tax offset read model persistence through runtime/executor boundaries.
- Keep `Application` as dependency assembly, HTTP/session wrapper, and compat-only delegate where still needed.
- Add or update a static guard proving broad `_persist_state(...)` no longer serializes `tax_offset_read_models`.
- Re-run relevant tax offset executor/static guard tests.
- Produce/update an analysis file documenting implementation evidence, old-path classification, state-machine impact, seven-category test applicability, verification and next boundary.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim `tax_offset` globally closed.
- Do not remove explicit runtime/executor persistence callbacks unless a replacement boundary already exists and is tested.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change tax business semantics, amount rules, certification rules, plan save API shape, permissions, audit meaning, worker event names, queue schema, Redis key/envelope contract or frontend behavior.

Expected verification:

- Targeted static guard proving `_persist_state(...)` no longer writes `tax_offset_read_models`.
- Relevant tax offset executor/API/runtime tests when touched.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified tax offset full-state snapshot quarantine implementation slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
