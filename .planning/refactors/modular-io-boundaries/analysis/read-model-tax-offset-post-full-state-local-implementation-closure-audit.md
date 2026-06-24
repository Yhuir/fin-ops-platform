# Read Model Tax Offset Post Full-State Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-post-full-state-local-implementation-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Previous State

`read-models:tax-offset-full-state-read-model-snapshot-quarantine` removed the broad `Application._persist_state(...)` write of `tax_offset_read_models` and kept the explicit `_persist_tax_offset_read_models_best_effort(...)` persistence callback for runtime/executor-owned read model writes.

This audit re-runs local closure after that quarantine. It must not claim global module closure. It may only decide whether there is still a local implementation gap that blocks deferring real production evidence.

## Evidence Inspected

CodeGraph and literal scans inspected:

- `TaxOffsetReadModelRepositoryPort`;
- `TaxOffsetSqlProjectionBuilder.rebuild_tax_offset_read_model_scope(...)`;
- `TaxOffsetQueryService`;
- `TaxOffsetRuntimeService`;
- `TaxOffsetWorkerRebuildExecutor`;
- `TaxOffsetDerivedLifecycleExecutor`;
- `TaxOffsetCacheWarmupExecutor`;
- `Application._persist_state(...)`;
- `Application._persist_tax_offset_read_models_best_effort(...)`;
- `Application.rebuild_tax_offset_read_model_scope(...)`;
- `Application._schedule_tax_offset_cache_warmup(...)`;
- runtime Redis fresh cache publishing;
- gateway-backed refresh enqueue paths;
- tax offset static guard, executor, SQL runtime and state-store tests;
- read-models and tax-offset module docs/tests.

## Accounted Local Support

| Area | Status | Evidence |
| --- | --- | --- |
| IO contract / repository port | Accounted | `TaxOffsetReadModelRepositoryPort` exposes only manifest-listed load/get/save methods. PostgreSQL state-store read/write wiring and projection save paths use the port. |
| Query fresh gate | Accounted | SQL reads use `ReadModelQueryGateway`; missing/unavailable SQL repository fails closed with refreshing/enqueue behavior instead of live rebuilding as fresh. |
| Force refresh / scope policy | Accounted | `tax_offset` accepts month/all scopes; `all` is fan-out control and worker expansion uses concrete month shards. |
| Operation barrier | Accounted | Plan save and certified import frontend flows wait on current-month `tax_offset` operation barrier before refetching. |
| Worker rebuild | Accounted | `TaxOffsetWorkerRebuildExecutor` owns rebuild, read model upsert, explicit persistence callback and fresh Redis month/summary cache publish. `Application.rebuild_tax_offset_read_model_scope(...)` is a thin delegate. |
| Derived lifecycle | Accounted | `TaxOffsetDerivedLifecycleExecutor` owns read model invalidation and month-cache clearing. App-owned helper methods are removed and guarded from returning. |
| Cache warmup | Accounted | `TaxOffsetCacheWarmupExecutor` owns env gate, job scheduling, run-job progress/success handling, read model upsert and explicit snapshot persistence. App helper is compat-only thin delegation. |
| Full-state persistence quarantine | Accounted | `Application._persist_state(...)` no longer serializes `tax_offset_read_models` or calls `_tax_offset_read_model_service.snapshot()`. A static guard prevents that broad writer from returning. |
| Explicit local persistence | Accounted | `_persist_tax_offset_read_models_best_effort(...)` remains as the injected runtime/executor persistence boundary and delegates to `state_store.save_tax_offset_read_models(...)` when available. |
| Compatibility bootstrap | Accounted as compat-only | `TaxOffsetReadModelService.from_snapshot(persisted_state.get("tax_offset_read_models"))` remains for existing local/Mongo snapshots; the broad full-state save path no longer replenishes it. |
| Permissions / audit / API shape | Accounted locally | Existing tax offset API, permission and audit tests remain the relevant guards; this slice changed no business rule, permission meaning, audit meaning or HTTP response shape. |
| Tests/docs | Accounted locally | Tax offset repository, fresh gate, executor, cache warmup, full-state quarantine and architecture guard coverage is documented in module test matrices. |

## Remaining Evidence Gaps

No additional local implementation gap was found in this audit. The remaining gaps are real environment evidence:

- real PostgreSQL read/write behavior for `read_model.tax_offset_read_models`;
- durable queue drain through `job.outbox_events` and `job.read_model_dirty_scopes`;
- real `tax-offset` worker service readiness and failure behavior;
- App Status readiness under real worker execution;
- Redis/RabbitMQ/systemd behavior in the deployed runtime;
- high-row performance under production-sized tax data;
- browser smoke against production-like data and auth.

These are not safe to prove automatically without staging/local `PGSQL_URL` or a user-approved production validation scenario. Per the production rules, this is a soft gate and must be recorded as `production-evidence-deferred`, not as module closure.

## Legacy / Pollution Classification

| Surface | Classification | Decision |
| --- | --- | --- |
| Broad `_persist_state(...)` tax offset read model snapshot write | removed | It no longer writes `tax_offset_read_models`; static guard protects the removal. |
| `_persist_tax_offset_read_models_best_effort(...)` | explicit persistence boundary | Retained as runtime/executor dependency. It is not a broad full-state writer. |
| `TaxOffsetReadModelService.from_snapshot(...)` bootstrap | compat-only load path | Retained for existing local/Mongo snapshots; deletion would be a separate compatibility decision. |
| `Application.rebuild_tax_offset_read_model_scope(...)` | compat-only thin delegate | Delegates to `TaxOffsetWorkerRebuildExecutor`. |
| `Application._schedule_tax_offset_cache_warmup(...)` | compat-only thin delegate | Delegates to `TaxOffsetCacheWarmupExecutor`. |
| Direct queue/cache truth | forbidden | No new direct business-service writes to `job.outbox_events`, `job.read_model_dirty_scopes` or fresh cache truth were introduced. |

## State Machine Impact

- `read-models:tax-offset-post-full-state-local-implementation-closure-audit` transitions to `production-evidence-deferred`.
- `tax_offset` moves from local `implementation-gap-open` to local support accounted, but the module remains `not-module-closed`.
- `tax_offset` is added to deferred modules with explicit real environment evidence gaps.
- Insert next boundary: `read-models:next-pilot-selection-after-tax-offset`.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- State-machine definitions do not change; this uses existing `production-evidence-deferred` and `not-module-closed` semantics.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | This audit changes no tax amount, certification, matching, plan, permission or idempotency business rule. Existing business tests remain unchanged. |
| 2. Service-layer tests | Regression evidence applies | Existing executor, state-store and architecture guard tests prove service/application ownership boundaries. No new service code changed in this audit. |
| 3. API contract tests | Not applicable | No HTTP response shape, status, permission or API behavior changed. |
| 4. Read model/cache/background job tests | Applicable as evidence | Existing tax offset SQL runtime, worker rebuild, derived lifecycle, cache warmup and full-state quarantine guards are the local evidence base. No new runtime behavior changed in this audit. |
| 5. Frontend component and interaction tests | Not applicable | No frontend code or interaction contract changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this audit slice | Real E2E worker/browser evidence is explicitly deferred because no staging/local PGSQL URL or approved production write scenario exists. |
| 7. Existing feature regression tests | Applicable as retained evidence | Existing API/runtime/static guard coverage remains the regression boundary. This audit adds no code path needing additional regression tests. |

## Verification

This slice is docs/accounting only. Required verification:

```bash
bash scripts/verify.sh docs
git diff --check
```

## Next Boundary

`read-models:next-pilot-selection-after-tax-offset`

Select the next non-Go modular IO/read model pilot from the remaining implementation-gap-open candidates. Do not select Go/Fiber/Go Worker while non-Go modular IO/read model implementation-pending or implementation-gap-open work remains.
