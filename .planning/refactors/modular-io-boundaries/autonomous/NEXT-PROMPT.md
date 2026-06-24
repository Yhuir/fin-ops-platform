# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:cost-statistics-full-state-read-model-snapshot-quarantine` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:cost-statistics-full-state-read-model-snapshot-quarantine`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `cost_statistics` is the ninth non-Go modular IO/read model pilot.
- `CostStatisticsReadModelRepositoryPort` owns the manifest-listed load/get/save read model boundary.
- SQL fresh gate, production repository unavailable behavior, special cost scope normalization, parent aggregate proof, primary `cost-statistics` worker ownership and `cost-tax` compatibility worker classification are locally accounted for.
- `CostStatisticsDerivedLifecycleExecutor` owns derived lifecycle invalidation, `pending_invoice_rules_changed` persist-empty behavior, no-warmup generic refresh fallback metadata and `enqueued_jobs` accounting.
- Warmup/retry/rebuild app methods are compat-only delegates to `CostStatisticsRuntimeService`.
- Broad `Application._persist_state(...)` no longer serializes `cost_statistics_read_models`.
- Explicit `_persist_cost_statistics_read_models_best_effort(...)` remains available for runtime/query persistence.
- Startup compatibility loading from existing local `cost_statistics_read_models` snapshots remains.
- `cost_statistics` is still `implementation-gap-open` until post-quarantine local closure audit re-checks current code.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:cost-statistics-post-full-state-local-implementation-closure-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-full-state-read-model-snapshot-quarantine.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-post-derived-local-implementation-closure-audit.md`
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
6. Use CodeGraph for structural lookup before any implementation decision.

## Boundary Scope

Target:

- Re-audit cost statistics local implementation closure after full-state snapshot quarantine.
- Confirm whether any app-owned, old full-state, legacy live-read, direct dirty/outbox, cache publish, read model persistence, worker rebuild, derived lifecycle or route-owned cost statistics support path remains.
- If no local implementation gap remains, record `production-evidence-deferred` / `not-module-closed` for `cost_statistics`, deferring only real PostgreSQL/worker/App Status/high-row/browser evidence.
- If a local implementation gap remains, keep `cost_statistics` as `implementation-gap-open`, insert the next narrow boundary before Go candidates, and do not defer production evidence yet.
- Update planning state, queue, journal, next prompt, master prompt and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not run Go admission while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
- Do not change cost attribution, project scope, export behavior, parent aggregate semantics, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning, API shape or frontend behavior.
- Do not remove explicit runtime/query persistence unless the audit proves it is dead and covered by tests; default is preserve.
- Do not remove startup compatibility loading in this audit unless there is a separate proven removal boundary.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted static guard for broad full-state read model snapshot quarantine.
- Relevant cost statistics runtime/SQL/derived lifecycle tests.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

Known unrelated verification issue:

- A broad `tests.test_platform_runtime_boundary_guards` run previously failed on two findings outside this slice:
  - `backend/src/fin_ops_platform/tools/repair_submitted_etc_invoice_overlaps.py` contains direct `update app.invoices` SQL.
  - `backend/src/fin_ops_platform/tools/oa_attachment_invoice_promotion.py` passes `allow_create` to OA attachment invoice upsert, and the server promotion guard does not find the expected `CREATE_INVOICE_AND_LINK` expression.
- Do not hide or relax these findings. Only fix them if the selected boundary explicitly expands to those platform guard issues.

## Stop Condition

Complete one verified post-full-state local closure audit slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
