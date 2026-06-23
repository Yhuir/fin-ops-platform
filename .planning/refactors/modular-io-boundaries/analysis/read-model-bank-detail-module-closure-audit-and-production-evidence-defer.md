# Bank Detail Module Closure Audit And Production Evidence Defer

**Date:** 2026-06-24
**Boundary:** `read-models:bank-detail-module-closure-audit-and-production-evidence-defer`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Decision

`bank_detail` cannot be marked `closed` or only `production-evidence-deferred` yet.

The module has meaningful local progress:

- repository/query access has a narrow `BankDetailReadModelRepositoryPort`;
- route/application read paths cover freshness/status behavior;
- write/force-refresh responses expose `read_model_scope_keys` and `freshness_targets`;
- stale/refreshing/schema mismatch behavior is covered by tests;
- unused SQL/read/cache helpers and the old category mutation side-effect callback have been removed from `Application`;
- category mutation side effects now go through `BankDetailCategoryMutationSideEffectPort`;
- refresh enqueue still goes through `ReadModelRefreshGateway` rather than direct queue SQL.

However, remaining `Application`-owned bank detail collaborators still prove the local implementation boundary is not fully closed:

- `Application._latest_bank_detail_auto_category_suggestion(...)` is still a compat-only read callback and reaches `_import_service`, `_bank_details_service._auto_category_input_row(...)`, and `_bank_transaction_auto_category_service`.
- `Application._enqueue_bank_detail_read_model_refreshes(...)` is still a gateway-backed wrapper that also publishes the Redis/wakeup cache invalidation wrapper.
- `Application._delete_bank_detail_redis_cache(...)` is still a gateway-adjacent wakeup wrapper.
- `Application._bank_detail_available_month_scope_keys(...)` still calculates fan-out scopes from import-service transactions.
- `Application._derived_lifecycle_bank_detail_executor(...)` still owns the derived lifecycle bank-detail executor wiring.
- `Application._bank_details_application_service(...)` is still a large dependency factory that injects the retained callbacks into `BankDetailsApplicationService`.

These are not necessarily bugs, but they are still local implementation boundaries that must be extracted, narrowed, or explicitly quarantined with deletion conditions before the read model pilot can be closed.

## Evidence

Targeted source audit found these current definitions/call sites in `backend/src/fin_ops_platform/app/server.py`:

- `_latest_bank_detail_auto_category_suggestion` at the bank detail transaction route area.
- `_enqueue_bank_detail_read_model_refreshes` and `_delete_bank_detail_redis_cache` near the read model enqueue wrappers.
- `_bank_details_application_service` injecting `suggestion_provider`, `available_month_scope_keys_provider`, `enqueue_bank_detail_refresh`, `enqueue_turnover_ledger_refresh`, and the explicit `BankDetailCategoryMutationSideEffectPort`.
- `_derived_lifecycle_bank_detail_executor` and `_bank_detail_available_month_scope_keys` in the derived lifecycle executor area.

Existing guard evidence in `tests/test_platform_runtime_boundary_guards.py` already classifies the retained callbacks and prevents removed helpers from returning. That guard is useful, but it is not the same as module closure.

## Production Evidence

Production evidence remains deferred and must not block autonomous local implementation progress because this repository still has:

- no local `PGSQL_URL`;
- no staging database;
- no safe automatic production write path;
- only root SSH for read-only or explicitly authorized production checks.

The missing production evidence includes real PostgreSQL dirty/outbox/readiness rows, real worker drain, App Status behavior, high-row historical data behavior, and browser smoke against production-like data. This is a release validation gap, not a reason to depend on staging/PGSQL_URL for every local refactor slice.

## Next Boundary

The next smallest implementation boundary should be:

`read-models:bank-detail-suggestion-provider-port-extraction`

Scope:

- move the latest auto-category suggestion callback out of `Application` into an explicit provider/port owned by services;
- keep API response shape, category suggestion semantics, permissions, audit and freshness behavior unchanged;
- add guard coverage that the old `Application._latest_bank_detail_auto_category_suggestion(...)` callback cannot return;
- do not touch Go/Fiber/Go Worker.

The refresh producer/lifecycle wrappers should stay visible as later boundaries after the suggestion provider is extracted.

## Seven Test Categories

This slice is analysis and planning state accounting only, so no runtime tests were added in this slice.

- Business core unit tests: not applicable; no classification or category rules changed.
- Service-layer tests: not applicable for this audit slice; the next implementation slice must add service/provider tests if behavior moves.
- API contract tests: not applicable; no API contract changed.
- Read model/cache/background job tests: not applicable; no refresh behavior changed.
- Frontend component and interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: not applicable; no cross-module runtime behavior changed.
- Existing feature regression tests: docs/state-only verification plus existing guard evidence is sufficient for this slice; next implementation slice must run bank detail API/service/read model regressions.

## Verification

Required for this slice:

- `bash scripts/verify.sh docs`
- `git diff --check`

