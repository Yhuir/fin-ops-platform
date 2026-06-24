# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-cache-warmup-executor-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-cache-warmup-executor-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- Repository port extraction is implemented.
- Freshness/barrier audit is implemented.
- OA attachment invoice `invoice_type` fallback is fixed.
- Worker rebuild extraction is implemented: `TaxOffsetWorkerRebuildExecutor` owns compat worker rebuild, read model persistence and fresh Redis cache publish behavior; `Application.rebuild_tax_offset_read_model_scope(...)` is a thin delegate.
- Derived lifecycle extraction is implemented: `TaxOffsetDerivedLifecycleExecutor` owns read model invalidation and month-cache clearing behavior; derived lifecycle registry entries use explicit executor methods and removed app-owned helper methods are guarded.
- Cache warmup extraction is implemented: `TaxOffsetCacheWarmupExecutor` owns optional cache warmup env gating, month normalization, idempotent job scheduling, run-job progress/success handling, read model upsert and snapshot persistence.
- `Application._schedule_tax_offset_cache_warmup(...)` remains compat-only thin delegation to the executor.
- `Application._run_tax_offset_cache_warmup_job(...)` and `_tax_offset_cache_warmup_enabled(...)` are removed and guarded from returning.
- `tax_offset` is still `implementation-gap-open` until final local closure audit proves all local implementation support is accounted for.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-final-local-implementation-closure-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-post-derived-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-cache-warmup-executor-port-extraction.md`
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

- Re-audit `tax_offset` after cache warmup extraction.
- Prove whether all local implementation support is accounted for across:
  - IO contract and public/internal boundary;
  - canonical fact owner and shared fact source;
  - repository port and query owner;
  - read model fresh gate, force refresh and `all` fan-out/month proof;
  - operation barrier after writes;
  - worker rebuild and derived lifecycle ownership;
  - optional cache warmup ownership;
  - legacy path removal or compat-only quarantine;
  - permission/audit/test/docs evidence.
- If no local implementation gap remains, mark only local implementation support as accounted for and move the module to `production-evidence-deferred` with explicit missing real PostgreSQL/worker/App Status/high-row/browser evidence.
- If a local implementation gap remains, do not defer. Insert the next narrow implementation boundary before Go candidates and set `tax_offset` to implementation-gap-open.
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

Complete one verified tax offset final local closure audit slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
