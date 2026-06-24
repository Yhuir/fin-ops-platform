# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:cost-statistics-refresh-freshness-operation-barrier-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:cost-statistics-refresh-freshness-operation-barrier-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `cost_statistics` is the ninth non-Go modular IO/read model pilot.
- `CostStatisticsReadModelRepositoryPort` owns the manifest-listed load/get/save read model boundary.
- Existing code/tests locally account for SQL fresh gate, production repository unavailable behavior, special cost scope normalization, parent aggregate proof, primary `cost-statistics` worker ownership and `cost-tax` compatibility worker classification.
- `Application._derived_lifecycle_cost_statistics_executor(...)` still owns derived lifecycle invalidation, warmup-vs-refresh fallback, metadata propagation and `enqueued_jobs` accounting.
- `cost_statistics` is still `implementation-gap-open`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:cost-statistics-derived-lifecycle-executor-port-extraction`

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

- Add a `CostStatisticsDerivedLifecycleExecutor` service.
- Move the behavior currently owned by `Application._derived_lifecycle_cost_statistics_executor(...)` behind that executor:
  - derive scope keys from lifecycle domain plan;
  - preserve `pending_invoice_rules_changed` `persist_empty` behavior;
  - call cost statistics runtime invalidation APIs;
  - preserve `schedule_warmup=False` generic refresh fallback and metadata propagation;
  - preserve `enqueued_jobs` accounting and return shape.
- Keep `Application` as dependency assembly and a thin delegate only.
- Add/update tests proving the old app-owned lifecycle executor logic cannot re-own the behavior.
- Update planning state, queue, journal, next prompt, master prompt and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not run Go admission while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
- Do not change cost attribution, project scope, export behavior, parent aggregate semantics, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning, API shape or frontend behavior.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted py_compile for changed backend/tests.
- Targeted cost statistics derived lifecycle executor/static guard tests.
- Relevant cost statistics SQL/runtime tests if behavior is touched.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified cost statistics derived lifecycle executor extraction slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
