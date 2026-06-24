# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:next-pilot-selection-after-cost-statistics` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:next-pilot-selection-after-cost-statistics`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `cost_statistics` local implementation support is accounted for after repository port, freshness/barrier audit, derived lifecycle executor extraction and full-state snapshot quarantine.
- `cost_statistics` is not globally closed; real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
- `turnover_ledger` is selected as the tenth non-Go read model implementation pilot.
- Remaining later non-Go read model candidates include `no_oa_bank_batch`, `search` and `bank_account_balance`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:turnover-ledger-repository-port-extraction`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-cost-statistics.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/implementation-notes.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`
   - `tests/test_turnover_ledger_query_service.py`
   - `tests/test_turnover_ledger_read_model_refresh.py`
   - `tests/test_read_model_manifest.py`
6. Use CodeGraph for structural lookup before implementation.

## Boundary Scope

Target:

- Add a narrow `TurnoverLedgerReadModelRepositoryPort`.
- Expose only manifest-listed methods:
  - `list_turnover_ledger_view`;
  - `save_turnover_ledger_rows`;
  - `clear_turnover_ledger_rows`.
- Wire `TurnoverLedgerQueryService` and `TurnoverLedgerSqlProjectionBuilder` read/save paths through the port.
- Return/use the port from PostgreSQL state-store or route/service read wiring where applicable.
- Add/update tests proving the port excludes unrelated read model methods and existing SQL runtime/freshness behavior remains unchanged.
- Update planning state, queue, journal, next prompt, master prompt and affected module docs/tests.

Forbidden:

- Do not change turnover business rules, grouped payload shape, manual closure semantics, Workbench relation command behavior, API shape, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning or frontend behavior.
- Do not move SQL table knowledge out of `PostgresReadModelRepository` in this slice.
- Do not implement Go/Fiber/Go Worker.
- Do not start broad global refactors.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted Python compile for touched backend/test files.
- Targeted turnover query/projection/worker tests, at minimum:
  - `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_read_model_refresh -v`
  - any new port guard test added in this slice.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified `turnover_ledger` repository-port extraction slice, commit and push to `origin/dev`, then continue to the next selected safe boundary unless a hard stop gate is hit.
