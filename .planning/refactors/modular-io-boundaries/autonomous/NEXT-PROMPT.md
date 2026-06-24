# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-derived-lifecycle-executor-boundary-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-derived-lifecycle-executor-boundary-audit`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- Repository port extraction is implemented.
- Freshness/barrier audit is implemented.
- OA attachment invoice `invoice_type` fallback is fixed.
- Worker rebuild extraction is implemented: `TaxOffsetWorkerRebuildExecutor` owns compat worker rebuild, read model persistence and fresh Redis cache publish behavior; `Application.rebuild_tax_offset_read_model_scope(...)` is a thin delegate.
- Derived lifecycle extraction is implemented: `TaxOffsetDerivedLifecycleExecutor` owns read model invalidation and month-cache clearing behavior; derived lifecycle registry entries use explicit executor methods and removed app-owned helper methods are guarded.
- `tax_offset` is still `implementation-gap-open` until the post-derived local closure/defer audit confirms no further local implementation gaps.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-post-derived-local-implementation-closure-audit`

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
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/implementation-notes.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
6. Use CodeGraph for structural lookup before any implementation edit.

## Boundary Scope

Target:

- Re-audit local `tax_offset` implementation closure after these slices:
  - repository port extraction;
  - freshness/operation-barrier audit and OA attachment invoice fallback;
  - worker rebuild executor extraction;
  - derived lifecycle executor extraction.
- Search for remaining app-owned or legacy-contaminating tax offset read model/read cache/worker/lifecycle support surfaces.
- Decide whether `tax_offset` can move to `production-evidence-deferred` for local implementation support, or whether another narrow implementation boundary is required first.
- If another implementation gap is found, document it and insert exactly one next narrow boundary before Go candidates.
- Produce/update an analysis file documenting evidence, decision, legacy/pollution classification, state-machine impact, seven-category test applicability and verification.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim `tax_offset` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change tax business semantics, amount rules, certification rules, plan save API shape, permissions, audit meaning, worker event names, queue schema, Redis key/envelope contract or frontend behavior.

Expected verification:

- For analysis-only: `bash scripts/verify.sh docs` and `git diff --check`.
- If implementation is required in the same selected boundary only after explicit split/accounting: targeted executor/static guard/tax offset tests.

## Stop Condition

Complete one verified tax offset post-derived local closure/defer audit or split, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
