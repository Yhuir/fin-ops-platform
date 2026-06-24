# Read Model Turnover Ledger Refresh Producer Clear Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:turnover-ledger-refresh-producer-clear-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`read-models:turnover-ledger-refresh-freshness-operation-barrier-audit` found that turnover SQL fresh gate, month/all scope policy, manifest/App Status/worker registration, Workbench relation source-version proof and operation barrier evidence already exist. The remaining local implementation gap was app-owned refresh/clear behavior in `Application`.

## Selected Boundary

Extract turnover read model refresh producer and clear behavior from `Application` into an explicit service boundary:

- Non-transactional refresh enqueue must still use `ReadModelRefreshGateway` and the registered `turnover_ledger` month/all scope policy.
- Best-effort clear must use the turnover-specific read model repository port, not broad `_workbench_sql_read_repository`.
- Existing turnover tag-selection, relation-extra, relation mutation invalidation and bank-detail side-effect callers must keep their observable refresh behavior.
- No turnover business rules, API response shapes, worker event names, queue schema, permissions, audit semantics, frontend behavior, Go/Fiber or Go Worker state may change.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_read_model_repository.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/bank_detail_category_side_effects.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_turnover_ledger_query_service.py`
- `tests/test_turnover_ledger_read_model_refresh.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Implementation

- Added `TurnoverLedgerReadModelRefreshProducer` with:
  - `enqueue(scope_keys, reason, metadata=None)` using `ReadModelRefreshGateway.enqueue_many("turnover_ledger", ...)`.
  - month/all scope cleanup equivalent to the removed app helper before gateway validation.
  - empty/invalid-only scope fallback to `all`, preserving legacy fallback behavior.
  - `clear_best_effort()` calling `clear_turnover_ledger_rows()` on the turnover-specific repository provider.
- Removed app-owned authoritative helpers:
  - `Application._enqueue_turnover_ledger_read_model_refreshes(...)`
  - `Application._clear_turnover_ledger_read_model_best_effort(...)`
- Wired existing callers to `Application._turnover_ledger_read_model_refresh_producer()`:
  - turnover tag-selection legacy fallback
  - turnover relation-extra legacy fallback
  - turnover relation mutation invalidation
  - bank detail category side effects
  - bank auto-tag settings finalizer
  - `BankDetailsApplicationService` factory callbacks
- Updated tests to attach turnover fake read repositories through `_turnover_ledger_sql_read_repository`, while keeping broad workbench slot setup where old tests still prove no direct clear on primary UoW paths.

## Legacy Classification

- Removed: app-owned turnover refresh enqueue helper.
- Removed: app-owned turnover clear helper.
- Retained compat-only: turnover legacy fallback facades still exist for local/non-postgres compatibility, but their read model side effects now call an explicit turnover producer boundary.
- Forbidden write scope: the producer does not write `job.outbox_events`, `job.read_model_dirty_scopes`, read model readiness, App Status or Redis directly. Durable enqueue stays behind `ReadModelRefreshGateway` and the queue repository.

## Seven-Category Test Decision

1. Business core unit tests: not applicable; no turnover business rule, relation validation, amount rule or status transition changed.
2. Service-layer tests: applicable and covered by `tests/test_turnover_ledger_read_model_refresh_producer.py`, which verifies producer enqueue/clear behavior.
3. API contract tests: not directly applicable; API response shape and HTTP status behavior were intentionally unchanged. Targeted turnover API regressions were run to prove no observable refresh behavior drift.
4. Read model/cache/background job tests: applicable and covered by producer tests plus turnover query/refresh regression tests.
5. Frontend component and interaction tests: not applicable; no frontend code or operation overlay contract changed.
6. End-to-end business-flow integration tests: not applicable for this narrow boundary; confirm/withdraw/tag-selection flows are protected by existing API/UoW tests.
7. Existing feature regression tests: applicable and covered by turnover API tests, bank auto-tag side-effect test and platform runtime boundary guards.

## State Impact

- Queue item `143` moves from `pending` to `implementation-closed`.
- `turnover_ledger` remains `implementation-gap-open` until a local implementation closure audit confirms there are no remaining local gaps.
- Insert next boundary: `read-models:turnover-ledger-local-implementation-closure-audit`.
- Go/Fiber/Go Worker admission remains `blocked-by-prerequisite`.
- State-machine definitions are unchanged; this slice updates progress/accounting only.

## Verification

Required verification for the completed slice:

- `python3 -m py_compile ...`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_model_refresh_producer -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_read_model_refresh_producers_use_scope_gateway_boundary -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_query_service tests.test_turnover_ledger_read_model_refresh ... -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_bank_auto_tag_rules_api.BankAutoTagRulesApiTests.test_bank_category_mutation_side_effect_port_enqueues_turnover_ledger_all_refresh -v`
- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check`
- `bash scripts/verify.sh docs`
- `git diff --check`

## Next Boundary

`read-models:turnover-ledger-local-implementation-closure-audit`
