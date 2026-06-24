# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:cost-statistics-derived-lifecycle-executor-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:cost-statistics-derived-lifecycle-executor-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `cost_statistics` is the ninth non-Go modular IO/read model pilot.
- `CostStatisticsReadModelRepositoryPort` owns the manifest-listed load/get/save read model boundary.
- Existing code/tests locally account for SQL fresh gate, production repository unavailable behavior, special cost scope normalization, parent aggregate proof, primary `cost-statistics` worker ownership and `cost-tax` compatibility worker classification.
- `CostStatisticsDerivedLifecycleExecutor` now owns derived lifecycle invalidation, `pending_invoice_rules_changed` persist-empty behavior, no-warmup generic refresh fallback metadata and `enqueued_jobs` accounting.
- `Application._derived_lifecycle_cost_statistics_executor(...)` has been removed and is guarded from returning.
- `cost_statistics` is still `implementation-gap-open`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:cost-statistics-post-derived-local-implementation-closure-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-derived-lifecycle-executor-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-refresh-freshness-operation-barrier-audit.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/cost-statistics/implementation-notes.md`
   - `docs/modules/cost-statistics/state-machine.md`
   - `docs/modules/cost-statistics/tests.md`
6. Use CodeGraph for structural lookup before implementation decisions.

## Boundary Scope

Target:

- Re-audit cost statistics local implementation closure after repository port, freshness/barrier and derived lifecycle executor extraction.
- Classify remaining cost statistics old surfaces:
  - `Application._schedule_cost_statistics_cache_warmup(...)`;
  - `Application._run_cost_statistics_cache_warmup_job(...)`;
  - retry/remaining-scope helper wrappers;
  - `Application.rebuild_cost_statistics_read_model_scope(...)`;
  - broad `Application._persist_state(...)` `cost_statistics_read_models` snapshot behavior;
  - `cost-tax` compatibility worker lane;
  - any remaining direct cache/readiness/dirty/outbox helper path.
- If a concrete local implementation gap remains, insert the next narrow implementation boundary before Go candidates.
- If no local implementation gap remains, record only real PostgreSQL/worker/App Status/high-row/browser evidence gaps and do not claim module closure unless full closure evidence exists.
- Update planning state, queue, journal, next prompt, master prompt and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not run Go admission while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
- Do not change cost attribution, project scope, export behavior, parent aggregate semantics, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning, API shape or frontend behavior unless a concrete audited gap requires a tested narrow fix.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted static guard/cost statistics tests if evidence depends on executable behavior.
- Relevant cost statistics SQL/runtime/derived lifecycle tests if local closure evidence depends on them.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

Known unrelated verification issue:

- A broad `tests.test_platform_runtime_boundary_guards` run currently fails on two findings outside this slice:
  - `backend/src/fin_ops_platform/tools/repair_submitted_etc_invoice_overlaps.py` contains direct `update app.invoices` SQL.
  - `backend/src/fin_ops_platform/tools/oa_attachment_invoice_promotion.py` passes `allow_create` to OA attachment invoice upsert, and the server promotion guard does not find the expected `CREATE_INVOICE_AND_LINK` expression.
- Do not hide or relax these findings. Only fix them if the selected boundary explicitly expands to those platform guard issues.

## Stop Condition

Complete one verified cost statistics post-derived local closure audit slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
