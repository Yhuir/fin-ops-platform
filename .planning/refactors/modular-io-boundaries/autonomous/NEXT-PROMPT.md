# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-invoice-lifecycle` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-invoice-lifecycle`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `invoice_lifecycle` local implementation support is accounted for after repository port, freshness/barrier and derived lifecycle executor slices.
- `invoice_lifecycle` is not globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable.
- `tax_offset` is selected as the next non-Go modular IO/read model pilot.
- `tax_offset` selection rationale: it directly consumes invoice lifecycle/certification state, has high stale-read risk after plan save/certified import/import fan-out, and has a narrow repository-port first slice.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-repository-port-extraction`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-invoice-lifecycle.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-invoice-lifecycle-local-implementation-closure-audit.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/implementation-notes.md`
   - `docs/modules/tax-offset/tests.md`
6. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Add a narrow tax offset read model repository port for the manifest-listed methods:
  - `load_tax_offset_read_models`
  - `get_tax_offset_view`
  - `save_tax_offset_read_models`
- Wire tax offset SQL read/query/projection paths that currently depend on broad `PostgresReadModelRepository` behavior through the narrow port.
- Keep `PostgresReadModelRepository` as the SQL/table owner during this transition.
- Preserve API shape, tax calculation rules, plan save behavior, certified import behavior, source-version semantics, worker event semantics, frontend behavior and production state.
- Add or update tests proving the tax offset port does not expose unrelated read model methods.
- Reuse existing tax offset SQL runtime/read model tests and keep the implementation slice narrow.
- Produce/update an analysis file documenting previous state, implementation, legacy/pollution classification, state-machine impact, seven-category test applicability and verification.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change tax business semantics, amount rules, certification rules, plan save API shape, permissions, audit meaning or frontend behavior.

Expected verification:

- Targeted tax offset repository/query/projection tests selected from `tests/test_tax_offset_sql_runtime.py`, `tests/test_tax_offset_read_model_service.py`, `tests/test_tax_offset_api.py` or an added port test.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` if app wiring changes.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified tax offset repository-port extraction slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
