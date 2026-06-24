# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:cost-statistics-post-derived-local-implementation-closure-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:cost-statistics-post-derived-local-implementation-closure-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `cost_statistics` is the ninth non-Go modular IO/read model pilot.
- `CostStatisticsReadModelRepositoryPort` owns the manifest-listed load/get/save read model boundary.
- SQL fresh gate, production repository unavailable behavior, special cost scope normalization, parent aggregate proof, primary `cost-statistics` worker ownership and `cost-tax` compatibility worker classification are locally accounted for.
- `CostStatisticsDerivedLifecycleExecutor` owns derived lifecycle invalidation, `pending_invoice_rules_changed` persist-empty behavior, no-warmup generic refresh fallback metadata and `enqueued_jobs` accounting.
- Warmup/retry/rebuild app methods are compat-only delegates to `CostStatisticsRuntimeService`.
- Broad `Application._persist_state(...)` still serializes `cost_statistics_read_models`.
- `cost_statistics` is still `implementation-gap-open`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:cost-statistics-full-state-read-model-snapshot-quarantine`

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
6. Use CodeGraph for structural lookup before implementation decisions.

## Boundary Scope

Target:

- Remove broad `Application._persist_state(...)` writes of `cost_statistics_read_models`.
- Keep explicit cost statistics read model persistence through `_persist_cost_statistics_read_models_best_effort(...)` and runtime/query service callbacks.
- Preserve local startup loading of existing persisted cost statistics read models unless evidence proves it can be safely removed in this narrow slice.
- Add/update a static architecture guard preventing broad full-state persistence of `cost_statistics_read_models` from returning.
- Update planning state, queue, journal, next prompt, master prompt and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not run Go admission while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
- Do not change cost attribution, project scope, export behavior, parent aggregate semantics, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning, API shape or frontend behavior.
- Do not remove explicit runtime/query persistence.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted py_compile for changed backend/tests.
- Targeted static guard for cost statistics broad full-state snapshot quarantine.
- Relevant cost statistics runtime/SQL/derived lifecycle tests.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

Known unrelated verification issue:

- A broad `tests.test_platform_runtime_boundary_guards` run currently fails on two findings outside this slice:
  - `backend/src/fin_ops_platform/tools/repair_submitted_etc_invoice_overlaps.py` contains direct `update app.invoices` SQL.
  - `backend/src/fin_ops_platform/tools/oa_attachment_invoice_promotion.py` passes `allow_create` to OA attachment invoice upsert, and the server promotion guard does not find the expected `CREATE_INVOICE_AND_LINK` expression.
- Do not hide or relax these findings. Only fix them if the selected boundary explicitly expands to those platform guard issues.

## Stop Condition

Complete one verified cost statistics full-state read model snapshot quarantine slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
