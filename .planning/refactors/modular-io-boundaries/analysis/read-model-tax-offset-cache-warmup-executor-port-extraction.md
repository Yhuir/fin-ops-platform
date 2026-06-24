# Read Model Tax Offset Cache Warmup Executor Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-cache-warmup-executor-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`tax_offset` had already completed local repository port, freshness/barrier, worker rebuild executor and derived lifecycle executor slices. The post-derived closure audit found one remaining local app-owned support surface:

- `Application._schedule_tax_offset_cache_warmup(...)` normalized warmup months, created the idempotent background job and dispatched execution.
- `Application._run_tax_offset_cache_warmup_job(...)` built month payloads, upserted `TaxOffsetReadModelService`, persisted read model snapshots and marked the background job succeeded or partial-success.
- `TaxOffsetRuntimeService` still needed a cache warmup callback for the fallback path where dirty-scope enqueue is unavailable after invalidation.

That meant `Application` was not only dependency assembly. It still owned background job execution and read model write-side support behavior.

## Selected Boundary

Move optional tax offset cache warmup scheduling and job execution into an explicit service/executor boundary while preserving existing behavior.

This slice intentionally did not change tax business rules, plan save rules, certification behavior, API shape, frontend behavior, worker event names, durable queue schema, Redis cache contracts, permissions or audit semantics.

## Inspected Call Graph

- CodeGraph context for tax offset cache warmup identified `TaxOffsetCacheWarmupExecutor`, `TaxOffsetRuntimeService.schedule_cache_warmup` callback usage and relevant tax offset runtime/API tests.
- Literal scans confirmed the remaining old app methods were `Application._schedule_tax_offset_cache_warmup(...)` and `_run_tax_offset_cache_warmup_job(...)`, plus the app-local env helper `_tax_offset_cache_warmup_enabled(...)`.
- Existing tests covered the optional env-gated app callback through `tests/test_tax_offset_api.py::TaxOffsetApiTests::test_tax_offset_cache_warmup_is_optional_and_environment_gated`.

## Implementation Evidence

Added `backend/src/fin_ops_platform/services/tax_offset_cache_warmup_executor.py`:

- `TaxOffsetCacheWarmupExecutor.schedule(...)` owns env gating, month normalization/reverse sorting, idempotency key construction, affected scopes/months, background job creation and job dispatch.
- `TaxOffsetCacheWarmupExecutor.run_job(...)` owns progress updates, payload loading, read model upsert, snapshot persistence and `succeeded` / `partial_success` completion.
- `TaxOffsetCacheWarmupExecutor.env_enabled()` owns `FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED`.

Updated `Application`:

- `_configure_tax_offset_application_services(...)` now assembles `TaxOffsetCacheWarmupExecutor`.
- `TaxOffsetRuntimeService` receives a callback that delegates to the executor.
- `_schedule_tax_offset_cache_warmup(...)` remains as a thin compat/test delegate.
- `_run_tax_offset_cache_warmup_job(...)` and `_tax_offset_cache_warmup_enabled(...)` are removed from `Application`.

## Preserved Contract

The executor preserves:

- env key: `FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED`;
- month filter: `YYYY-MM`;
- reverse sorted de-duplication;
- idempotency key shape: `tax_offset_cache_warmup:{reason}:{months}`;
- job type: `tax_offset_cache_warmup`;
- label: `预热税金抵扣缓存`;
- owner: `system`;
- visibility: `system`;
- queued phase/message/result summary/source;
- affected scopes and affected months;
- progress phase `build_tax_offset_cache`;
- progress message shape `正在预热税金抵扣缓存 {index}/{total}。`;
- read model upsert with `cache_status="ready"` and source scope set to the month;
- persist operation name `tax_offset_cache_warmup`;
- final success messages and result summary shape.

## Legacy / Pollution Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `Application._schedule_tax_offset_cache_warmup(...)` | compat-only thin delegate | Kept for existing tests/callers; static guard forbids job creation, job execution, upsert, snapshot or env ownership inside the helper body. |
| `Application._run_tax_offset_cache_warmup_job(...)` | removed | Static guard forbids the helper from returning. |
| `Application._tax_offset_cache_warmup_enabled(...)` | removed | Env gate moved to executor; static guard forbids the app helper from returning. |
| `TaxOffsetCacheWarmupExecutor` | new owner | Unit tests and static guard prove it owns schedule/run/upsert/persist/progress/success behavior. |

## State Machine Impact

- `read-models:tax-offset-cache-warmup-executor-port-extraction` transitions from `pending` to `implementation-closed`.
- `tax_offset` remains `implementation-gap-open` until a final local closure audit re-runs against the current code and confirms no remaining local implementation gaps.
- No global state-machine definitions changed; `03-REFACTOR-STATE-MACHINE.md` and `docs/modules/tax-offset/state-machine.md` definitions remain valid because this slice uses existing `implementation-closed` semantics.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not directly applicable | No tax amount, certification, plan, matching or permission rule changed. Existing tax service tests remain the business-rule coverage. |
| 2. Service-layer tests | Applicable | Added `tests/test_tax_offset_cache_warmup_executor.py` to cover executor scheduling and run-job side effects. |
| 3. API contract tests | Regression applicable | Re-ran targeted tax offset API cache warmup test to prove app callback behavior remains compatible. |
| 4. Read model/cache/background job tests | Applicable | New executor test covers background job contract, read model upsert and snapshot persistence; architecture guard proves ownership moved out of `Application`. |
| 5. Frontend component and interaction tests | Not applicable | No frontend contract or user-visible page behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this narrow slice | No import/plan-save/user flow contract changed; real worker drain remains production-evidence-deferred. |
| 7. Existing feature regression tests | Applicable | Targeted tax offset API regression and static guard protect old callback behavior and prevent old app-owned execution from returning. |

## Verification

Initial targeted verification passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/tax_offset_cache_warmup_executor.py tests/test_tax_offset_cache_warmup_executor.py tests/test_read_model_architecture_guards.py tests/test_tax_offset_api.py
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_cache_warmup_executor -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_tax_offset_cache_warmup_is_explicit_executor_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_tax_offset_api.TaxOffsetApiTests.test_tax_offset_cache_warmup_is_optional_and_environment_gated -v
```

Final slice verification must also run app check/docs/diff checks before commit.

## Next Boundary

`read-models:tax-offset-final-local-implementation-closure-audit`

The next slice should re-audit `tax_offset` after cache warmup extraction and either:

- move local implementation support to `production-evidence-deferred` with explicit production evidence gaps, or
- identify the next concrete implementation gap and insert that gap before Go admission.
