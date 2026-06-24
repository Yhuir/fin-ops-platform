# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:cost-statistics-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:cost-statistics-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `cost_statistics` is the ninth non-Go modular IO/read model pilot.
- `CostStatisticsReadModelRepositoryPort` now owns the manifest-listed load/get/save read model boundary.
- PostgreSQL state-store cost statistics SQL read wiring returns the port.
- `CostStatisticsSqlProjectionBuilder` saves cost statistics read models through the port.
- `cost_statistics` is still `implementation-gap-open`; repository port extraction is only the first local slice.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:cost-statistics-refresh-freshness-operation-barrier-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-tax-ledger-summary-contract.md`
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

- Audit cost statistics freshness and operation-barrier local support after repository port extraction.
- Cover:
  - SQL fresh gate and production repository unavailable behavior;
  - `active:YYYY-MM` / `all:YYYY-MM` month shard semantics;
  - `active:all` / `all:all` queryable parent aggregate proof;
  - force refresh normalization and legacy naked scope quarantine;
  - parent scope missing/stale shard behavior;
  - operation barrier target registration and frontend write-after-read relevance;
  - `cost-statistics` primary worker vs `cost-tax` compatibility worker;
  - remaining app-owned helper/runtime/cache warmup surfaces;
  - old live/cache fallback classification;
  - permissions, audit, tests and docs evidence.
- If a concrete local implementation gap is found, insert the next narrow implementation boundary before Go candidates.
- If no local gap remains, record only real production evidence gaps and do not claim module closure unless full closure evidence exists.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not run Go admission while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
- Do not change cost attribution, project scope, export behavior, parent aggregate semantics, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning, API shape or frontend behavior unless a concrete gap requires a tested narrow fix.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted static guard/cost statistics tests if evidence depends on executable behavior.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified cost statistics freshness/barrier audit slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
