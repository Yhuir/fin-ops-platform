# Tax Offset Worker Rebuild Executor Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-worker-rebuild-executor-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

- `read-models:tax-offset-local-implementation-closure-audit` found that `Application.rebuild_tax_offset_read_model_scope(...)` still owned tax offset worker rebuild, read model persistence and fresh Redis cache publish behavior.
- This blocked moving `tax_offset` to `production-evidence-deferred`.
- The target boundary was intentionally narrow: move the worker rebuild behavior into an explicit executor/service boundary while preserving the existing in-memory/compat payload, persistence and cache contracts.

## Implementation

Runtime code:

- Added `backend/src/fin_ops_platform/services/tax_offset_worker_rebuild_executor.py`.
- `TaxOffsetWorkerRebuildExecutor` now owns:
  - month scope validation via `TaxOffsetRuntimeService.request_scope_key(...)`;
  - month payload loading through an injected `month_payload_loader`;
  - source-version lookup through `TaxOffsetRuntimeService.expected_source_versions()`;
  - `TaxOffsetReadModelService.upsert_read_model(...)`;
  - `snapshot_scope_keys(...)` persistence through an injected `persist_read_models` callback;
  - fresh Redis month and summary cache envelope publishing through `TaxOffsetRuntimeService`;
  - returned `scope_key`, `month` and `entry_count`.
- `Application._configure_tax_offset_application_services(...)` now assembles the executor after `TaxApiRoutes` is created.
- `Application.rebuild_tax_offset_read_model_scope(...)` is now a thin delegate to `self._tax_offset_worker_rebuild_executor.rebuild_scope(scope_key)`.
- Removed the no-longer-used `build_fresh_cache_envelope` import from `server.py`.

Tests:

- Added `tests/test_tax_offset_worker_rebuild_executor.py` covering:
  - read model persistence;
  - changed scope keys and operation name;
  - fresh month cache envelope;
  - fresh summary cache envelope;
  - `entry_count`;
  - invalid non-month scope rejection.
- Updated `tests/test_read_model_architecture_guards.py`:
  - direct fresh allowlist now classifies `TaxOffsetWorkerRebuildExecutor._publish_fresh_cache(...)` instead of `Application.rebuild_tax_offset_read_model_scope(...)`;
  - added a static guard proving the app method no longer contains `upsert_read_model`, persistence, fresh cache envelope or direct `read_model_status` writes;
  - classified existing output invoice collection relation detail fresh aliases that the guard surfaced during full static verification.

## Preserved Behavior

- No tax amount calculation, certification import, plan save API, API response shape, worker event name, queue schema, SQL projection builder, frontend behavior or Go/Fiber/Go Worker behavior changed.
- Existing production SQL worker path through `TaxOffsetSqlProjectionBuilder` remains unchanged.
- Existing app method name remains for compatibility with worker/projection-builder style call sites; it is now a thin delegate.
- Redis fresh cache envelope shape and TTL remain sourced from the existing runtime service.
- Minimal `Application.__new__` test fixtures remain supported by using `getattr(..., None)` during executor assembly, matching existing lazy app patterns.

## Legacy / Pollution Classification

| Path | Classification | Notes |
| --- | --- | --- |
| `TaxOffsetWorkerRebuildExecutor` | new explicit boundary | Owns compat/in-memory worker rebuild and fresh cache publish behavior. |
| `Application.rebuild_tax_offset_read_model_scope(...)` | compat-only thin delegate | Must not rebuild, persist, publish fresh cache or assign fresh status directly. |
| `TaxOffsetSqlProjectionBuilder.rebuild_tax_offset_read_model_scope(...)` | SQL production projection owner retained | Not changed in this slice. |
| `_derived_lifecycle_tax_offset_executor(...)` | remaining app-owned support surface | Still needs a separate boundary audit before local closure/defer can be reconsidered. |
| `_derived_lifecycle_tax_offset_month_cache_executor(...)` | remaining app-owned cache support surface | Must be audited with the derived lifecycle boundary. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/tax-offset/state-machine.md`

No global or module state definition changed. This slice changes implementation ownership only.

Transition:

- Previous queue item: `read-models:tax-offset-worker-rebuild-executor-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:tax-offset-derived-lifecycle-executor-boundary-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not applicable. No tax math, certification, identity, selection or plan-save rule changed. |
| 2. Service-layer tests | Covered. `tests.test_tax_offset_worker_rebuild_executor` verifies executor persistence/cache/result contracts. |
| 3. API contract tests | Covered by rerunning `tests.test_tax_offset_api`; no API shape changed. |
| 4. Read model/cache/background job tests | Covered by executor tests, `tests.test_tax_offset_sql_runtime`, and architecture guard tests. |
| 5. Frontend component and interaction tests | Not applicable. No frontend behavior changed. Existing operation barrier tests remain valid. |
| 6. End-to-end business-flow integration tests | Not applicable for this local ownership move. Real worker drain remains production evidence/defer scope after local gaps close. |
| 7. Existing feature regression tests | Covered by tax offset API/runtime and static architecture guard regressions. |

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/tax_offset_worker_rebuild_executor.py backend/src/fin_ops_platform/app/server.py tests/test_tax_offset_worker_rebuild_executor.py tests/test_read_model_architecture_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_worker_rebuild_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_tax_offset_worker_rebuild_is_explicit_executor_boundary tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_direct_fresh_status_assignments_are_explicitly_classified -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only tax offset worker rebuild executor extraction. It does not close `tax_offset`, production evidence, derived lifecycle executor accounting, the read model roadmap or any Go hot-path gate.
