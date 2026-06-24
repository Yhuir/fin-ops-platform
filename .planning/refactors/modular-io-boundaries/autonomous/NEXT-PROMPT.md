# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-post-derived-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-post-derived-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- Repository port extraction is implemented.
- Freshness/barrier audit is implemented.
- OA attachment invoice `invoice_type` fallback is fixed.
- Worker rebuild extraction is implemented: `TaxOffsetWorkerRebuildExecutor` owns compat worker rebuild, read model persistence and fresh Redis cache publish behavior; `Application.rebuild_tax_offset_read_model_scope(...)` is a thin delegate.
- Derived lifecycle extraction is implemented: `TaxOffsetDerivedLifecycleExecutor` owns read model invalidation and month-cache clearing behavior; derived lifecycle registry entries use explicit executor methods and removed app-owned helper methods are guarded.
- Post-derived local closure audit found a remaining app-owned cache warmup support surface: `Application._schedule_tax_offset_cache_warmup(...)` and `_run_tax_offset_cache_warmup_job(...)` still normalize/cache-warm months, create background jobs, build tax payloads, upsert `TaxOffsetReadModelService` and persist read model snapshots.
- `tax_offset` is still `implementation-gap-open`; it cannot move to `production-evidence-deferred` until the cache warmup boundary is extracted or explicitly quarantined.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-cache-warmup-executor-port-extraction`

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

- Move optional tax offset cache warmup scheduling/job execution out of `Application` into an explicit executor/service boundary, or prove and document a stricter compat-only quarantine if extraction is not currently safe.
- Keep `Application` as dependency assembly and thin delegate/callback provider only.
- Preserve:
  - `FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED` env gating;
  - month normalization and reverse ordering;
  - idempotency key shape `tax_offset_cache_warmup:{reason}:{months}`;
  - background job type, label, owner, visibility, phase, source, affected scopes and affected months;
  - progress messages and final `succeeded` / `partial_success` result shape;
  - payload load behavior through the existing tax route/service boundary;
  - read model upsert/persist operation name `tax_offset_cache_warmup`;
  - no tax business/API/UI/worker event/queue/schema/Redis contract changes.
- Add executor/service tests and static guard coverage proving `Application` no longer owns payload build, upsert or read model persistence for cache warmup.
- Produce/update an analysis file documenting implementation evidence, legacy/pollution classification, state-machine impact, seven-category test applicability and verification.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim `tax_offset` globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change tax business semantics, amount rules, certification rules, plan save API shape, permissions, audit meaning, worker event names, queue schema, Redis key/envelope contract or frontend behavior.

Expected verification:

- Targeted new executor/service tests.
- Targeted static guard proving app cache warmup methods are thin/delegating or removed.
- Relevant tax offset API/runtime tests covering optional cache warmup and SQL runtime non-regression.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified tax offset cache warmup executor extraction/quarantine slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
