# Read Model Bank Account Balance Refresh Freshness Operation Barrier Audit

**Date:** 2026-06-24
**Boundary:** `read-models:bank-account-balance-refresh-freshness-operation-barrier-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit `bank_account_balance` refresh enqueue paths, derived lifecycle ownership, all-only scope behavior, operation barrier evidence and the remaining Bank Detail compatibility fallback after repository port extraction.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-account-balance-repository-port-extraction.md`
- `docs/modules/bank-account-balance/README.md`
- `docs/modules/bank-account-balance/state-machine.md`
- `docs/modules/bank-account-balance/tests.md`
- `docs/modules/bank-account-balance/implementation-notes.md`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_repository.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/runtime_worker_handlers.py`
- `backend/src/fin_ops_platform/app/bank_account_balance_backfill.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_bank_account_balance_read_model.py`
- `tests/test_bank_details_sql_runtime.py`
- `tests/test_bankdetail_backfill_cli.py`
- `tests/test_operation_freshness_barrier.py`
- `tests/test_read_model_refresh_gateway.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- CodeGraph context for `BankAccountBalanceReadModelRefreshService` and related refresh/derived lifecycle patterns.

## Findings

### 1. Refresh enqueue is still app-owned

`Application._enqueue_bank_account_balance_read_model_refresh(...)` still owns non-transactional refresh enqueue for the account-balance read model. It does call `ReadModelRefreshGateway.enqueue_one("bank_account_balance", "all", ...)`, so it is not bypassing the durable queue, but the module-specific IO boundary still lives in `Application`.

Known callers:

- Bank Details accounts fresh gate through `BankDetailsApplicationService` injection.
- Import-state invalidation paths when bank detail scopes are affected.
- `_derived_lifecycle_bank_account_balance_executor(...)`.

This matches the prior Search pattern before `SearchReadModelRefreshProducer` extraction. The next concrete implementation slice should extract `BankAccountBalanceReadModelRefreshProducer` and make app/Bank Details/import-state paths use it.

### 2. Derived lifecycle execution is still app-owned

`Application._derived_lifecycle_bank_account_balance_executor(...)` still constructs the invalidation result and enqueued-job accounting directly. It currently always invalidates `["all"]`, which matches the worker/storage all-only contract, but the ownership remains in app code.

This should not be extracted before the refresh producer. The derived lifecycle executor can become a small follow-up slice that depends on the explicit producer boundary.

### 3. Runtime import-state fan-out still uses a generic enqueue helper

`RuntimeWorkerHandlers.invalidate_import_state(...)` enqueues `bank_account_balance` through `_enqueue_scopes("bank_account_balance", ["all"], reason="import_state_changed")` when bank detail scopes are affected. That remains gateway-backed through the runtime queue path, but it bypasses a bank-account-balance-specific producer boundary.

The producer extraction slice should include this runtime worker import-state path, or split it as the immediate follow-up if the first producer slice is kept server/app-only.

### 4. Worker/storage contract is all-only, while scope policy currently accepts month/all

`BankAccountBalanceReadModelRefreshService.handle_runtime_event(...)` rejects anything except `scope_type="bank_account_balance"` and `scope_key="all"`. `docs/modules/bank-account-balance/state-machine.md` records `bank_account_balance:all` as the only publish scope. However, `DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY["bank_account_balance"]` currently uses the generic month-or-all policy, so the gateway can accept month scopes that the worker will reject later.

Do not introduce month/account projection shards as part of this audit. A later scope-contract slice must either tighten `bank_account_balance` to all-only at the gateway or document and guard month scopes as invalid before enqueue.

### 5. Operation barrier evidence is registered but not dedicated

The manifest and App Status registries include `bank_account_balance`, and the operation barrier can consume generic read model targets. Existing operation barrier tests prove exact-scope behavior for other read models, and registry tests cover worker/read-model registration parity.

There is no dedicated `bank_account_balance:all` operation barrier regression yet. After the producer extraction and scope policy decision, add a focused operation barrier regression that proves pending `bank_account_balance:all` outbox/dirty state keeps the Bank Details accounts target refreshing.

### 6. Bank Detail compatibility fallback remains transition-only

`BankDetailsApplicationService.accounts_payload(...)` now prefers `BankAccountBalanceReadModelRepositoryPort`, but can still fall back to `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` when no explicit account-balance port is injected. That fallback is currently a transition compatibility path, not the target owner.

It should remain visible as an implementation gap until either removed or guarded as compat-only with a clear deletion condition.

## Decision

Next boundary:

`read-models:bank-account-balance-refresh-producer-extraction`

Scope:

- Add `BankAccountBalanceReadModelRefreshProducer`.
- Keep enqueue behind `ReadModelRefreshGateway`.
- Preserve all-only behavior by normalizing every enqueue to `bank_account_balance:all`.
- Route `Application` import-state paths and Bank Details service injection through the producer.
- Include runtime import-state fan-out if the change stays small; otherwise split it into the next producer-boundary follow-up.
- Do not change account balance calculation, API shape, permissions, audit behavior, frontend behavior, worker event type, queue schema or storage table.
- Do not introduce month/account scopes.

Follow-up boundaries after producer extraction:

- `read-models:bank-account-balance-derived-lifecycle-executor-extraction`
- `read-models:bank-account-balance-all-only-scope-contract`
- `read-models:bank-account-balance-operation-barrier-regression`
- `read-models:bank-account-balance-compat-fallback-quarantine`

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable for audit | No balance, account identity, currency, sorting or filtering rules changed. |
| 2. Service-layer tests | Applies to next implementation | Producer extraction must add service tests proving gateway-backed all-scope enqueue and no unrelated scope behavior. |
| 3. API contract tests | Existing coverage applies | `/api/bank-details/accounts` shape is unchanged; producer extraction must preserve fresh/refreshing payloads. |
| 4. Read model/cache/background job tests | Applies to next implementation | Producer, runtime import-state fan-out, worker all-only behavior and backfill enqueue coverage must be kept. |
| 5. Frontend component and interaction tests | Not applicable for audit | No UI behavior changed. |
| 6. End-to-end business-flow integration tests | Environment evidence deferred | Bank import -> durable refresh -> account balance fresh still requires real PostgreSQL/worker evidence. |
| 7. Existing feature regression tests | Applies | Bank Details accounts SQL runtime, manifest, runtime worker registry and backfill tests remain the regression net. |

## State Machine Impact

- `read-models:bank-account-balance-refresh-freshness-operation-barrier-audit` transitions to `analysis-closed`.
- `bank_account_balance` remains `implementation-gap-open`.
- Insert next boundary `read-models:bank-account-balance-refresh-producer-extraction`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_bank_account_balance_read_model tests.test_bank_details_sql_runtime tests.test_bankdetail_backfill_cli tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```
