# Next Prompt

Continue the autonomous modular IO refactor after the `read-models:turnover-ledger-refresh-producer-clear-port-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `read-models:turnover-ledger-refresh-producer-clear-port-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- `turnover_ledger` is the tenth non-Go read model implementation pilot.
- `TurnoverLedgerReadModelRepositoryPort` is implemented and wired into PostgreSQL state-store read wiring, app query injection and worker projection save paths.
- Turnover freshness/barrier audit found local support evidence for SQL fresh gate, month/all scope policy, manifest/App Status/worker registration, Workbench relation source-version proof and operation barrier targets.
- `TurnoverLedgerReadModelRefreshProducer` now owns non-transactional turnover refresh enqueue and best-effort clear.
- Turnover refresh enqueue stays behind `ReadModelRefreshGateway` and the `turnover_ledger` scope policy.
- Turnover clear uses `_turnover_ledger_sql_read_repository.clear_turnover_ledger_rows()` through the turnover-specific port, not broad `_workbench_sql_read_repository`.
- Removed app-owned authoritative helpers:
  - `Application._enqueue_turnover_ledger_read_model_refreshes(...)`
  - `Application._clear_turnover_ledger_read_model_best_effort(...)`
- `turnover_ledger` is not globally closed.
- Remaining later non-Go read model candidates include `no_oa_bank_batch`, `search` and `bank_account_balance`.
- No Go hot-path candidate has passed admission.
- Go hot-path candidates remain `blocked-by-prerequisite`.

## Next Boundary

`read-models:turnover-ledger-local-implementation-closure-audit`

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
   - `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-refresh-producer-clear-port-extraction.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/implementation-notes.md`
   - `docs/modules/read-models/tests.md`
   - `docs/modules/turnover-ledger/README.md`
   - `docs/modules/turnover-ledger/implementation-notes.md`
   - `docs/modules/turnover-ledger/tests.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh_producer.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_read_model_repository.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`
   - `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
   - `backend/src/fin_ops_platform/services/bank_details_application_service.py`
   - `tests/test_turnover_ledger_read_model_refresh_producer.py`
   - `tests/test_turnover_ledger_query_service.py`
   - `tests/test_turnover_ledger_api.py`
   - `tests/test_read_model_architecture_guards.py`
   - `tests/test_platform_runtime_boundary_guards.py`
6. Use CodeGraph for structural lookup before declaring closure or selecting another implementation boundary.

## Boundary Scope

Target:

- Audit all remaining local `turnover_ledger` implementation surfaces after repository port, freshness/barrier audit and refresh producer/clear extraction.
- Confirm whether remaining server/service callbacks are dependency assembly, explicit ports, compat-only local fallback, or still implementation gaps.
- Check route/service/repository/read model/worker/front-end API legacy paths for unclassified authoritative behavior.
- Check read model freshness, force refresh, operation barrier, source-version proof, repository port, dirty/outbox and App Status evidence.
- Check permission/audit/test/docs contracts relevant to `turnover_ledger`.
- If no local implementation gap remains, move local support to `production-evidence-deferred` without claiming global module closure.
- If a concrete local implementation gap remains, queue exactly one next narrow boundary before production evidence defer.
- Update planning state, queue, journal, next prompt, master prompt and affected module docs/tests.

Forbidden:

- Do not change turnover business rules, grouped payload shape, manual closure semantics, Workbench relation command behavior, API shape, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning or frontend behavior.
- Do not implement Go/Fiber/Go Worker.
- Do not start broad global refactors.
- Do not depend on staging DB or local `PGSQL_URL`.
- Do not perform production writes or read/print secrets.

Expected verification:

- Targeted static/rg/codegraph evidence for remaining turnover local surfaces.
- Any targeted tests needed by the audit result.
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified turnover local implementation closure audit slice, commit and push to `origin/dev`, then continue to the next selected safe boundary unless a hard stop gate is hit.
