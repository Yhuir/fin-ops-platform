# Read Model Bank Account Balance Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:bank-account-balance-local-implementation-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Goal

Re-audit the `bank_account_balance` read model after repository port extraction, refresh producer extraction, derived lifecycle executor extraction, all-only scope policy enforcement, operation barrier regressions and Bank Detail fallback quarantine.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-producer-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-derived-lifecycle-executor-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-all-only-scope-contract.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-operation-barrier-regression.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-bank-detail-fallback-quarantine.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/bank-account-balance/state-machine.md`
- `docs/modules/bank-account-balance/tests.md`
- `docs/modules/bank-account-balance/implementation-notes.md`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh_producer.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `backend/src/fin_ops_platform/app/bank_account_balance_backfill.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `tests/test_bank_details_sql_runtime.py`
- `tests/test_bank_account_balance_read_model.py`
- `tests/test_bank_account_balance_derived_lifecycle_executor.py`
- `tests/test_read_model_refresh_gateway.py`
- `tests/test_operation_freshness_barrier.py`
- `tests/test_runtime_worker_read_model_refresh_scopes.py`
- `tests/test_bankdetail_backfill_cli.py`
- `tests/test_runtime_bootstrap.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Local Closure Finding

No remaining local implementation gap was found for `bank_account_balance`.

Local evidence now covers:

- **Repository port:** `BankAccountBalanceReadModelRepositoryPort` owns manifest-listed scope summary/list/save methods, and the Bank Details accounts SQL path uses that explicit port.
- **Projection save:** `BankAccountBalanceProjectionBuilder` persists through the narrow account-balance port.
- **Refresh enqueue:** Application, Bank Details service injection, runtime import-state fan-out, runtime derived lifecycle fan-out and backfill enqueue route through `BankAccountBalanceReadModelRefreshProducer`.
- **Scope contract:** `ReadModelRefreshGateway` rejects non-`all` `bank_account_balance` scopes before durable enqueue, matching the worker/storage all-only contract.
- **Derived lifecycle:** `BankAccountBalanceDerivedLifecycleExecutor` owns account-balance derived lifecycle response assembly and preserves all-only payload shape.
- **Worker handler:** `BankAccountBalanceReadModelRefreshService` accepts only `scope_type=bank_account_balance` and `scope_key=all`, rebuilds the projection and completes the same scope.
- **Operation barrier:** dedicated regressions prove dirty/readiness and pending outbox state keep `bank_account_balance:all` refreshing, while unrelated outbox state does not block the target.
- **Legacy contamination:** `BankDetailReadModelRepositoryPort` no longer exposes `list_bank_account_balances(...)`; a platform guard prevents the fallback from returning.
- **Runtime/bootstrap behavior:** production SQL runtime with a missing account-balance table returns refreshing and enqueues `bank_account_balance:all` instead of falling back to legacy service/live rows.

## Deferred Evidence

The module is not globally closed. These evidence classes remain unavailable in the current environment and are explicitly deferred:

- Real PostgreSQL migration/table/readiness evidence.
- Real worker drain from `job.outbox_events` / `job.read_model_dirty_scopes` to fresh `read_model.app_status_readiness`.
- App Status runtime snapshot evidence from production-like data.
- High-row performance evidence for account-balance projection/list reads.
- Browser smoke evidence for Bank Details accounts after real import/worker refresh.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Covered | Account identity, latest balance and currency normalization remain covered by `tests/test_bank_account_balance_read_model.py`. |
| 2. Service-layer tests | Covered | Bank Details service, repository port, producer and derived lifecycle executor tests cover service boundaries. |
| 3. API contract tests | Covered locally | Runtime bootstrap/API path tests cover production SQL runtime fallback prevention and refreshing payload behavior. |
| 4. Read model/cache/background job tests | Covered locally | Refresh service, gateway scope policy, operation barrier, worker registry and backfill CLI tests cover local contracts. |
| 5. Frontend component and interaction tests | Not changed | No frontend behavior changed in this pilot. Existing Bank Details page coverage remains outside this slice. |
| 6. End-to-end business-flow integration tests | Deferred | Real import -> worker -> accounts fresh browser evidence needs production/staging-like runtime. |
| 7. Existing feature regression tests | Covered | Static platform guards and manifest tests prevent old fallback, broad producer bypass and manifest drift from returning. |

## State Machine Impact

- `read-models:bank-account-balance-local-implementation-closure-audit` transitions to `production-evidence-deferred`.
- `bank_account_balance` local implementation support is accounted for but the module remains `not-module-closed`.
- No Go implementation is started in this slice.
- Insert `go-hot-path:performance-baseline-and-admission-reconciliation` as the next planning boundary before any Go/Fiber/Go Worker implementation.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_details_sql_runtime tests.test_bank_account_balance_read_model tests.test_bank_account_balance_derived_lifecycle_executor tests.test_read_model_refresh_gateway tests.test_operation_freshness_barrier tests.test_runtime_worker_read_model_refresh_scopes tests.test_bankdetail_backfill_cli tests.test_runtime_bootstrap tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_refresh_producer_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_derived_lifecycle_uses_explicit_executor_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_accounts_path_does_not_fallback_to_bank_detail_port -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
