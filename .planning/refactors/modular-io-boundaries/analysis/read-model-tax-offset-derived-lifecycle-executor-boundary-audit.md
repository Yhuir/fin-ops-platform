# Tax Offset Derived Lifecycle Executor Boundary Audit

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-derived-lifecycle-executor-boundary-audit`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

- `read-models:tax-offset-worker-rebuild-executor-port-extraction` moved compat worker rebuild, read model persistence and fresh Redis cache publish behavior out of `Application.rebuild_tax_offset_read_model_scope(...)`.
- The remaining local `tax_offset` implementation gap was app-owned derived lifecycle execution:
  - `Application._derived_lifecycle_tax_offset_executor(...)`;
  - `Application._derived_lifecycle_tax_offset_month_cache_executor(...)`;
  - derived lifecycle registry entries for `tax_offset_read_model` and `tax_offset_month_cache`.
- Similar read model lifecycle executors already existed for `bank_detail`, `workbench_relation` and `invoice_lifecycle`, so the local architecture direction favored an explicit executor/service boundary over leaving implementation behavior in `Application`.

## Evidence Reviewed

- CodeGraph surfaced existing explicit executor patterns:
  - `BankDetailDerivedLifecycleExecutor`;
  - `WorkbenchRelationDerivedLifecycleExecutor`;
  - `InvoiceLifecycleDerivedLifecycleExecutor`.
- `server.py` registry still mapped:
  - `"tax_offset_read_model": self._derived_lifecycle_tax_offset_executor`;
  - `"tax_offset_month_cache": self._derived_lifecycle_tax_offset_month_cache_executor`.
- The app-owned methods still selected scopes, called tax offset invalidation/cache behavior, built result payloads and emitted `enqueued_jobs`.
- `TaxOffsetRuntimeService` already owned the reusable invalidate/read model/cache/warmup methods needed by the executor.

## Implementation

Runtime code:

- Added `backend/src/fin_ops_platform/services/tax_offset_derived_lifecycle_executor.py`.
- `TaxOffsetDerivedLifecycleExecutor.execute_read_model(...)` now owns:
  - domain-plan scope normalization;
  - `all` vs explicit-scope read model invalidation;
  - default reason `derived_lifecycle_tax_offset`;
  - result shape with `deleted_counts`, `invalidated_scopes` and `enqueued_jobs`.
- `TaxOffsetDerivedLifecycleExecutor.execute_month_cache(...)` now owns:
  - lifecycle scope month extraction;
  - `all` vs month-specific cache clearing;
  - result shape for `tax_offset_month_cache`.
- `Application` now registers:
  - `"tax_offset_read_model": self._tax_offset_derived_lifecycle_executor().execute_read_model`;
  - `"tax_offset_month_cache": self._tax_offset_derived_lifecycle_executor().execute_month_cache`.
- Removed the app-owned `_derived_lifecycle_tax_offset_executor(...)` and `_derived_lifecycle_tax_offset_month_cache_executor(...)` methods.

Tests:

- Added `tests/test_tax_offset_derived_lifecycle_executor.py` covering:
  - explicit read model scope invalidation with forwarded reason;
  - empty-scope behavior preserved as no-op invalidation, not implicit `all`;
  - explicit `all` invalidation;
  - month cache clear for extracted lifecycle months;
  - month cache clear-all behavior.
- Updated `tests/test_platform_runtime_boundary_guards.py` with a static guard proving:
  - old app-owned methods are removed;
  - `server.py` builds `TaxOffsetDerivedLifecycleExecutor`;
  - derived lifecycle registry uses explicit executor methods;
  - executor preserves read model and month cache result contracts.

## Preserved Behavior

- No tax amount calculation, certification import, plan save API, API response shape, worker event name, queue schema, SQL projection builder, Redis key/envelope contract, frontend behavior or Go/Fiber/Go Worker behavior changed.
- Empty tax offset lifecycle scope behavior is preserved: it calls explicit-scope invalidation with an empty list and returns no invalidated scopes.
- `all` still means full read model invalidation for `tax_offset_read_model` and full cache clear for `tax_offset_month_cache`.
- Month extraction still accepts any `YYYY-MM` segment within lifecycle scope keys.

## Legacy / Pollution Classification

| Path | Classification | Notes |
| --- | --- | --- |
| `TaxOffsetDerivedLifecycleExecutor` | new explicit boundary | Owns tax offset derived lifecycle read model/cache execution. |
| `Application._tax_offset_derived_lifecycle_executor(...)` | dependency assembly | Builds the explicit executor with runtime service and month-cache clearer. |
| `Application._derived_lifecycle_tax_offset_executor(...)` | removed legacy/app-owned implementation | Guarded from returning. |
| `Application._derived_lifecycle_tax_offset_month_cache_executor(...)` | removed legacy/app-owned implementation | Guarded from returning. |
| `tax_offset_read_model` derived lifecycle registry entry | explicit executor method | Uses `execute_read_model`. |
| `tax_offset_month_cache` derived lifecycle registry entry | explicit executor method | Uses `execute_month_cache`. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/tax-offset/state-machine.md`

No global or module state definition changed. This slice changes implementation ownership only.

Transition:

- Previous queue item: `read-models:tax-offset-derived-lifecycle-executor-boundary-audit`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:tax-offset-post-derived-local-implementation-closure-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not applicable. No tax math, certification, identity, selection or plan-save rule changed. |
| 2. Service-layer tests | Covered. `tests.test_tax_offset_derived_lifecycle_executor` verifies executor scope/cache/result contracts. |
| 3. API contract tests | Covered by rerunning `tests.test_tax_offset_api`; no API route or response shape changed, and the certified-import confirm regression now asserts the current lifecycle event boundary. |
| 4. Read model/cache/background job tests | Covered by executor tests, derived lifecycle service regression and platform runtime boundary guard. |
| 5. Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this local ownership move. Existing derived lifecycle tests cover event plan contracts; real worker drain remains production evidence/defer scope. |
| 7. Existing feature regression tests | Covered by `tests.test_derived_data_lifecycle_service` and platform guard regression. |

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/tax_offset_derived_lifecycle_executor.py backend/src/fin_ops_platform/app/server.py tests/test_tax_offset_derived_lifecycle_executor.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_derived_lifecycle_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_tax_offset_derived_lifecycle_uses_explicit_executor_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_derived_data_lifecycle_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

Attempted broader guard:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards -v
```

The broader guard still fails on two unrelated pre-existing platform guard findings outside this slice:

- `backend/src/fin_ops_platform/tools/repair_submitted_etc_invoice_overlaps.py` contains direct `update app.invoices` SQL.
- `backend/src/fin_ops_platform/tools/oa_attachment_invoice_promotion.py` passes `allow_create` to OA attachment invoice upsert, and the existing server promotion guard does not find the expected `CREATE_INVOICE_AND_LINK` expression.

The targeted tax offset derived lifecycle guard passed.

## Completion Claim

This slice closes only tax offset derived lifecycle executor extraction. It does not close `tax_offset`, production evidence, the broader read model roadmap or any Go hot-path gate. The next slice must re-audit local `tax_offset` implementation closure after repository port, freshness/barrier, worker rebuild executor and derived lifecycle executor extraction are all present.
