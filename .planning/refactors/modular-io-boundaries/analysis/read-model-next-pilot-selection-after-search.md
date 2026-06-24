# Read Model Next Pilot Selection After Search

**Date:** 2026-06-24
**Boundary:** `read-models:next-pilot-selection-after-search`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Select the next non-Go read model pilot after Search local support moved to `production-evidence-deferred`.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-search-post-all-scope-worker-fanout-local-implementation-closure-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-bank-detail-and-bank-account-balance-contract.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/bank_detail_read_model_repository.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_projection.py`
- `backend/src/fin_ops_platform/services/bank_account_balance_read_model_refresh.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `backend/src/fin_ops_platform/app/bank_account_balance_backfill.py`
- `backend/src/fin_ops_platform/postgres/migrations/0039_bank_account_balance_read_model.sql`
- `tests/test_bank_account_balance_read_model.py`
- `tests/test_bank_details_sql_runtime.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`
- `tests/test_read_model_slo_smoke.py`
- CodeGraph context and impact for `bank_account_balance` and `BankDetailReadModelRepositoryPort`.

## Selection

Select `bank_account_balance` as the thirteenth non-Go read model pilot.

## Rationale

`bank_account_balance` is now the remaining known read model candidate after Search. It is narrower than the previous page-level pilots, but it is user-visible on Bank Details accounts, participates in bank import write-operation SLO, has an independent event/table/worker contract, and has documented rules that balance amount/readiness must not be derived from bank detail rows.

Existing support:

- Manifest declares `bank_account_balance` as `partitioned_scoped_incremental`, event `bank_account_balance.read_model.refresh`, worker `bank-account-balance`, query owner `BankDetailsApplicationService`, permission owner `bank_details_api_session`, and test owner `tests/test_bank_account_balance_read_model.py`.
- Runtime worker registry has a required `bank-account-balance` worker for `bank_account_balance.read_model.refresh`.
- Backfill CLI can dry-run, enqueue, rebuild, and drain the worker handler.
- Projection tests cover stable account identity, latest balance selection, currency normalization, direct balance table reads and empty fresh payload behavior.
- Import-state invalidation already enqueues `bank_account_balance:all` for bank imports.

Current implementation gaps:

- `BankAccountBalanceProjectionBuilder` writes through broad `PostgresReadModelRepository` instead of a narrow `BankAccountBalanceReadModelRepositoryPort`.
- `BankDetailReadModelRepositoryPort` still exposes `list_bank_account_balances(...)` as a transition dependency for Bank Details accounts response shape. This keeps the balance read model coupled to the bank detail read-side port.
- `BankDetailsApplicationService.accounts_payload(...)` reads account balance payloads through the bank detail SQL repository surface, so the query path does not yet receive an explicit account-balance read model dependency.
- `Application._enqueue_bank_account_balance_read_model_refresh(...)` and `_derived_lifecycle_bank_account_balance_executor(...)` still own refresh enqueue / derived lifecycle behavior.
- Scope policy currently accepts month or `all`, while the worker refresh service and storage summary only accept `bank_account_balance:all`. This contract mismatch must be accounted before local closure; do not introduce month scopes without a separate design.

## First Boundary

Queue `read-models:bank-account-balance-repository-port-extraction`.

First-boundary intent:

- Add a narrow `BankAccountBalanceReadModelRepositoryPort` exposing only manifest-listed methods:
  - `bank_account_balance_scope_summary(...)`
  - `list_bank_account_balances(...)`
  - `save_bank_account_balances(...)`
- Route `BankAccountBalanceProjectionBuilder` save path through the narrow port.
- Route Bank Details accounts SQL read path through the explicit account-balance port while preserving the existing response shape and compatibility behavior.
- Keep `BankDetailReadModelRepositoryPort.list_bank_account_balances(...)` as compat-only or remove it only if call graph/tests prove the explicit account-balance port covers all callers.
- Add/extend tests proving account-balance port does not expose bank detail/pending/search/no-OA/workbench methods and Bank Details accounts behavior remains unchanged.

## Non-Goals

- Do not implement Go/Fiber/Go Worker.
- Do not change balance calculation rules, account identity rules, API response shape, worker event names, queue schema, permissions, audit behavior, or frontend behavior.
- Do not convert `bank_account_balance` to month/account scoped writes in this slice.
- Do not claim module closure; this is only pilot selection.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable for selection | No balance/account identity rule changed in this slice. |
| 2. Service-layer tests | Applies to next implementation | Repository port extraction must update/add account-balance service/repository tests. |
| 3. API contract tests | Applies to next implementation if accounts query wiring changes | Bank Details accounts response shape and refreshing/fresh status must remain covered. |
| 4. Read model/cache/background job tests | Applies to next implementation | Projection save path, worker refresh, scope policy and App Status contracts must remain covered. |
| 5. Frontend component and interaction tests | Not applicable for this selection | No frontend behavior changed; add only if account page UI behavior changes later. |
| 6. End-to-end business-flow integration tests | Deferred | Bank import -> account balance refresh remains production/staging evidence for later. |
| 7. Existing feature regression tests | Applies to next implementation | Existing bank details SQL runtime, account balance read model, backfill CLI, manifest and runtime worker tests form the regression net. |

## State Machine Impact

- `read-models:next-pilot-selection-after-search` transitions to `analysis-closed`.
- `bank_account_balance` becomes the next selected non-Go read model pilot and remains `implementation-gap-open`.
- Insert next boundary: `read-models:bank-account-balance-repository-port-extraction`.
- Go/Fiber/Go Worker admission remains blocked.

## Verification

Passed:

```bash
bash scripts/verify.sh docs
git diff --check
```
