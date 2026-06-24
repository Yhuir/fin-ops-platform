# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:turnover-ledger-refresh-freshness-operation-barrier-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:turnover-ledger-refresh-freshness-operation-barrier-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `turnover_ledger` is the tenth non-Go read model implementation pilot.
- `TurnoverLedgerReadModelRepositoryPort` is implemented and wired into PostgreSQL state-store read wiring, app query injection and worker projection save paths.
- The audit found local support evidence for SQL fresh gate, month/all scope policy, manifest/App Status/worker registration, Workbench relation source-version proof and operation barrier targets.
- The audit also found a concrete implementation gap: `Application._enqueue_turnover_ledger_read_model_refreshes(...)` and `_clear_turnover_ledger_read_model_best_effort(...)` still own turnover refresh/clear behavior, and clear still goes through broad `_workbench_sql_read_repository`.
- `turnover_ledger` is not globally closed.
- Remaining later non-Go read model candidates include `no_oa_bank_batch`, `search` and `bank_account_balance`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:turnover-ledger-refresh-producer-clear-port-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile:
   - `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/JOURNAL.md`
   - `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-repository-port-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-refresh-freshness-operation-barrier-audit.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/implementation-notes.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/bank_detail_category_side_effects.py`
   - `backend/src/fin_ops_platform/services/bank_details_application_service.py`
   - `tests/test_turnover_ledger_query_service.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_read_model_architecture_guards.py`
6. Use CodeGraph for structural lookup before implementation.

## Boundary Scope

Target:

- Extract turnover read model refresh producer behavior out of `Application._enqueue_turnover_ledger_read_model_refreshes(...)`.
- Extract or reroute turnover read model clear behavior so it uses the turnover-specific repository port, not broad `_workbench_sql_read_repository`.
- Preserve `ReadModelRefreshGateway` / scope policy boundary for non-transactional refresh.
- Preserve existing callback behavior for bank detail category side effects, turnover mutation invalidation and settings/tag updates.
- Add/update tests proving the old app-owned clear/enqueue helpers cannot re-own authoritative behavior and that scope normalization/refresh enqueue behavior is unchanged.
- Update planning state, queue, journal, next prompt, master prompt and affected module docs/tests.

Forbidden:

- Do not change turnover business rules, grouped payload shape, manual closure semantics, Workbench relation command behavior, API shape, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not start broad global refactors.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted Python compile for touched backend/test files.
- Targeted turnover/bank detail read model producer tests added or updated in this slice.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified turnover refresh producer / clear port extraction slice, commit and push to `origin/dev`, then continue to the next selected safe boundary unless a hard stop gate is hit.
