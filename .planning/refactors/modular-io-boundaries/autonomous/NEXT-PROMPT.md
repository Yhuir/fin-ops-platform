# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:turnover-ledger-repository-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:turnover-ledger-repository-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `turnover_ledger` is the tenth non-Go read model implementation pilot.
- `TurnoverLedgerReadModelRepositoryPort` now exposes only `list_turnover_ledger_view`, `save_turnover_ledger_rows` and `clear_turnover_ledger_rows`.
- PostgreSQL state-store turnover read wiring, `TurnoverLedgerQueryService` app injection and worker projection save paths use the narrow turnover port.
- `turnover_ledger` is not globally closed; freshness/barrier, force refresh, all-scope proof, Workbench relation source-version proof, operation barrier targets and legacy contamination still need audit.
- Remaining later non-Go read model candidates include `no_oa_bank_batch`, `search` and `bank_account_balance`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:turnover-ledger-refresh-freshness-operation-barrier-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-cost-statistics.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/implementation-notes.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/services/read_model_manifest.py`
   - `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_source_versions.py`
   - `tests/test_turnover_ledger_query_service.py`
   - `tests/test_turnover_ledger_read_model_refresh.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_operation_freshness_barrier.py`
6. Use CodeGraph for structural lookup before implementation.

## Boundary Scope

Audit and account for:

- `turnover_ledger` fresh gate behavior.
- Force refresh and scope policy behavior.
- `all` fan-out versus queryable read behavior.
- Workbench relation source-version proof and non-fresh handling.
- Operation barrier targets used by turnover write-after-read flows.
- Any legacy read path or app-owned helper that can bypass the new port or read stale/live data as fresh.
- Whether concrete implementation gaps must be split into a follow-up boundary before local closure/defer accounting.

Forbidden:

- Do not change turnover business rules, grouped payload shape, manual closure semantics, Workbench relation command behavior, API shape, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning or frontend behavior unless the audit finds a concrete bug and the next boundary is explicitly split.
- Do not implement Go/Fiber/Go Worker.
- Do not start broad global refactors.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- If analysis-only: `bash scripts/verify.sh docs` and `git diff --check`.
- If implementation is split and executed: run targeted turnover query/refresh/API/operation-barrier tests covering the changed boundary, then `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified turnover freshness/barrier/legacy contamination audit slice. If the audit finds a concrete implementation gap, update the queue with the next smallest implementation boundary instead of claiming local closure. Commit and push to `origin/dev`, then continue to the next selected safe boundary unless a hard stop gate is hit.
