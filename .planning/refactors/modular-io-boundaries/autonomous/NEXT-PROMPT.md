# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-tax-offset` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-tax-offset`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` local implementation support is accounted for but not globally closed; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `cost_statistics` is selected as the ninth non-Go modular IO/read model pilot.
- `cost_statistics` has high cross-page stale-read risk, special `active/all` scope grammar, queryable parent aggregate semantics and an old `cost-tax` compatibility worker lane.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:cost-statistics-repository-port-extraction`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-tax-offset.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-tax-ledger-summary-contract.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/cost-statistics/README.md`
   - `docs/modules/cost-statistics/implementation-notes.md`
   - `docs/modules/cost-statistics/state-machine.md`
   - `docs/modules/cost-statistics/tests.md`
6. Use CodeGraph for structural lookup before implementation.

## Boundary Scope

Target:

- Add a narrow `CostStatisticsReadModelRepositoryPort`.
- Expose only manifest-listed methods:
  - `load_cost_statistics_read_models`;
  - `get_cost_statistics_view`;
  - `save_cost_statistics_read_models`.
- Wire PostgreSQL state-store cost statistics read wiring to return/use the port where applicable.
- Wire `CostStatisticsQueryService` and `CostStatisticsSqlProjectionBuilder` read/save paths through the port.
- Add/update tests proving the port excludes unrelated read model methods and existing SQL runtime/freshness behavior remains unchanged.
- Update state machine/accounting/docs for the completed slice.

Forbidden:

- Do not change cost attribution, project scope, export behavior, parent aggregate semantics, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning, API shape or frontend behavior.
- Do not move SQL table knowledge out of `PostgresReadModelRepository` in this slice.
- Do not implement Go/Fiber/Go Worker.
- Do not run Go admission while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted py_compile for changed backend/tests.
- Targeted cost statistics SQL runtime / repository port tests.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified cost statistics repository port extraction slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
