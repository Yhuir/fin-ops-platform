# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:tax-offset-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:tax-offset-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `tax_offset` is the eighth non-Go modular IO/read model pilot.
- `TaxOffsetReadModelRepositoryPort` now exposes only:
  - `load_tax_offset_read_models`
  - `get_tax_offset_view`
  - `save_tax_offset_read_models`
- PostgreSQL state-store tax read/write wiring uses the narrow port.
- `PostgresStateStore.tax_offset_sql_read_repository` returns the narrow port over the optional SQL read connection.
- `TaxOffsetSqlProjectionBuilder` saves rebuilt month scopes through the narrow tax offset port.
- `tax_offset` is not globally closed because freshness, force refresh, all fan-out/month proof, operation barrier, legacy/live fallback and app-owned helper contamination still need audit.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:tax-offset-refresh-freshness-operation-barrier-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-invoice-lifecycle.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/11-GO-HOT-PATH-CARVE-OUT.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/tax-offset/README.md`
   - `docs/modules/tax-offset/implementation-notes.md`
   - `docs/modules/tax-offset/state-machine.md`
   - `docs/modules/tax-offset/tests.md`
6. Use CodeGraph for structural lookup before implementation edits.

## Boundary Scope

Target:

- Audit tax offset freshness/fresh gate behavior for SQL view miss, stale source/schema, refreshing, failed/unavailable and Redis cache eligibility.
- Audit force refresh contract and scope normalization for `tax_offset`, including month-only query scope and fan-out-only `all`.
- Audit all fan-out/month proof in `TaxOffsetReadModelRefreshService`, runtime worker dispatch and dirty/outbox/readiness semantics.
- Audit operation barrier behavior for plan save and certified import/write-after-read flows.
- Classify touched legacy/live/app-owned paths as removed, quarantined, compat-only or blocked-by-human-gate.
- Specifically check whether broad tax API regression failure `TaxOffsetApiTests.test_tax_offset_includes_oa_attachment_invoice_rows_by_issue_month` is pre-existing, already covered by a different path, or a real local gap to split into a narrow follow-up.
- Produce/update an analysis file documenting previous state, audit findings, implementation or split decision, legacy/pollution classification, state-machine impact, seven-category test applicability and verification.
- Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, `prompts/04-master-goal-controller.md`, and affected module docs/tests.

Forbidden:

- Do not implement Go/Fiber/Go Worker.
- Do not claim any module globally closed.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.
- Do not change tax business semantics, amount rules, certification rules, plan save API shape, permissions, audit meaning or frontend behavior unless the audit finds a concrete bug and the fix is split narrowly with tests.

Expected verification:

- Targeted tax offset read model/API/runtime tests selected from `tests/test_tax_offset_sql_runtime.py`, `tests/test_tax_offset_read_model_service.py`, `tests/test_tax_offset_api.py`, `tests/test_read_model_refresh_gateway.py`, `tests/test_runtime_worker_read_model_refresh_scopes.py` and frontend operation barrier tests if frontend wait logic is touched.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` if app wiring changes.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified tax offset freshness/force-refresh/operation-barrier audit slice, commit and push to `origin/dev`, then continue to the next safe boundary unless a hard stop gate is hit.
