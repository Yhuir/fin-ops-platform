# Read Model Bank Account Balance All-Only Scope Contract

**Date:** 2026-06-24
**Boundary:** `read-models:bank-account-balance-all-only-scope-contract`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Align `bank_account_balance` gateway scope validation with its worker/storage contract: `bank_account_balance:all` is the only valid publish scope.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-derived-lifecycle-executor-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-producer-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-refresh-freshness-operation-barrier-audit.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/bank-account-balance/state-machine.md`
- `docs/modules/bank-account-balance/tests.md`
- `docs/modules/bank-account-balance/implementation-notes.md`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh_producer.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
- `tests/test_read_model_refresh_gateway.py`
- `tests/test_bank_account_balance_read_model.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Changes

- Added an all-only read model scope policy helper.
- Changed `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY["bank_account_balance"]` from month-or-all to all-only.
- Added gateway tests proving `bank_account_balance:all` is accepted and duplicate-deduped.
- Added gateway tests proving month, account and active-style scopes are rejected before durable queue enqueue.
- Kept `BankAccountBalanceReadModelRefreshProducer` unchanged; it already normalizes every request to `["all"]`.

## Preserved Behavior

- `bank_account_balance:all` remains the only publish scope.
- No month/account projection shard was introduced.
- Balance calculation, account identity, API response shape, worker event type, queue schema, storage table behavior, permissions, audit and frontend behavior are unchanged.
- Other month-or-all read models keep their existing scope policy.

## Remaining Local Gaps

- Dedicated `bank_account_balance:all` operation barrier regression is still missing.
- `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` remains a transition compatibility fallback.
- Real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No balance or account classification rule changed. |
| 2. Service-layer tests | Applies | Gateway/scope-policy tests cover the enqueue boundary contract. |
| 3. API contract tests | Existing coverage applies | No route or response shape changed. |
| 4. Read model/cache/background job tests | Applies | Gateway tests prove invalid scopes cannot reach durable queue; existing worker tests continue to prove all-only worker behavior. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Environment evidence deferred | Bank import -> durable refresh -> account balance fresh still requires real PostgreSQL/worker evidence. |
| 7. Existing feature regression tests | Applies | Existing producer/manifest/static guard tests continue to protect producer and registry behavior. |

## State Machine Impact

- `read-models:bank-account-balance-all-only-scope-contract` transitions to `implementation-closed`.
- `bank_account_balance` remains `implementation-gap-open`.
- Insert next boundary `read-models:bank-account-balance-operation-barrier-regression`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_refresh_gateway tests.test_bank_account_balance_read_model tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_refresh_producer_helpers_stay_out_of_application tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_account_balance_derived_lifecycle_uses_explicit_executor_boundary tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
