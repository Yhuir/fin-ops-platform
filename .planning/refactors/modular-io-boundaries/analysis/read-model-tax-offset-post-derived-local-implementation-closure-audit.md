# Tax Offset Post-Derived Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-post-derived-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

- `TaxOffsetReadModelRepositoryPort` was extracted and wired through PostgreSQL state-store read/write paths and SQL projection save paths.
- Tax offset freshness/barrier behavior was audited: SQL reads use the fresh gate, missing SQL repository fails closed in production runtime, `all` refresh fans out to month shards, plan save rejects non-fresh/source-mismatched reads, and the frontend waits on the current-month operation barrier after plan save/certified import.
- `TaxOffsetWorkerRebuildExecutor` moved compat worker rebuild, read model persistence and fresh Redis month/summary cache publishing out of `Application.rebuild_tax_offset_read_model_scope(...)`.
- `TaxOffsetDerivedLifecycleExecutor` moved tax offset derived lifecycle read model invalidation and month-cache clearing out of removed app-owned helper methods.
- The current slice had to decide whether local `tax_offset` implementation support can move to `production-evidence-deferred`, or whether another local implementation gap remains.

## Evidence Reviewed

Planning and module evidence:

- `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-local-implementation-closure-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-worker-rebuild-executor-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-tax-offset-derived-lifecycle-executor-boundary-audit.md`
- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/tax-offset/README.md`
- `docs/modules/tax-offset/implementation-notes.md`
- `docs/modules/tax-offset/state-machine.md`
- `docs/modules/tax-offset/tests.md`

Code evidence:

- CodeGraph context for tax offset repository port, query/runtime service, worker rebuild executor, derived lifecycle executor, refresh service, SQL projection builder and `Application` tax offset surfaces.
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/tax_offset_runtime_service.py`
- `backend/src/fin_ops_platform/services/tax_offset_worker_rebuild_executor.py`
- `backend/src/fin_ops_platform/services/tax_offset_derived_lifecycle_executor.py`
- `backend/src/fin_ops_platform/services/tax_offset_read_model_refresh.py`
- `tests/test_read_model_architecture_guards.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_tax_offset_api.py`
- `tests/test_tax_offset_sql_runtime.py`

## Accounted Local Evidence

Repository port:

- `TaxOffsetReadModelRepositoryPort` exposes only `load_tax_offset_read_models`, `get_tax_offset_view` and `save_tax_offset_read_models`.
- `PostgresStateStore.tax_offset_sql_read_repository` returns the narrow port.
- `TaxOffsetSqlProjectionBuilder` persists rebuilt month scopes through the narrow port.

Freshness, force refresh and operation barrier:

- `TaxOffsetQueryService` uses `ReadModelQueryGateway` for SQL fresh-gated reads with schema/source-version proof and source-versioned Redis keys.
- Production SQL runtime with missing SQL repository returns refreshing/unavailable and enqueues refresh instead of live rebuilding.
- `TaxOffsetReadModelRefreshService` owns `tax_offset.read_model.refresh` handling; `all` is a fan-out command that enqueues concrete month shards and completes the parent dirty scope without publishing an `all` payload.
- `TaxOffsetPlanService` rejects non-fresh, scope-mismatched or source-version-mismatched read models before saving a plan.
- `TaxOffsetPage` waits on current-month `tax_offset` operation barrier after plan save and certified import.

Worker rebuild and derived lifecycle ownership:

- `Application.rebuild_tax_offset_read_model_scope(...)` is now a thin delegate to `TaxOffsetWorkerRebuildExecutor.rebuild_scope(scope_key)`.
- `TaxOffsetWorkerRebuildExecutor` owns compat worker rebuild, read model persistence and fresh Redis month/summary cache publication.
- `TaxOffsetDerivedLifecycleExecutor` owns read model invalidation and month-cache clearing result shapes.
- Removed app-owned `_derived_lifecycle_tax_offset_executor(...)` and `_derived_lifecycle_tax_offset_month_cache_executor(...)` methods are guarded from returning.

## Remaining Local Gap

`Application` still owns optional tax offset cache warmup job implementation:

- `_schedule_tax_offset_cache_warmup(...)` normalizes months, creates idempotent `tax_offset_cache_warmup` background jobs, computes affected scopes and dispatches the job.
- `_run_tax_offset_cache_warmup_job(...)` builds month payloads through `TaxApiRoutes.get_tax_offset(...)`, upserts `TaxOffsetReadModelService`, persists changed read model snapshots and marks the background job succeeded/partial success.
- `TaxOffsetRuntimeService` still receives `schedule_cache_warmup=self._schedule_tax_offset_cache_warmup` and uses it as fallback when dirty scope enqueue is unavailable after invalidation.
- The behavior is environment-gated by `FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED`, but it is not dead code and is covered by tests as optional behavior.

This is heavier than dependency assembly. It is an app-owned read model/cache support surface that can rebuild payloads, upsert read models and persist read model snapshots. It therefore cannot be hidden under `production-evidence-deferred`.

## Legacy / Pollution Classification

| Path | Classification | Decision |
| --- | --- | --- |
| `TaxOffsetReadModelRepositoryPort` | explicit boundary | Accounted. |
| `TaxOffsetQueryService` SQL fresh gate | explicit boundary | Accounted. |
| `TaxOffsetReadModelRefreshService` | worker refresh boundary | Accounted for local/fake evidence. Real worker drain remains production evidence. |
| `TaxOffsetWorkerRebuildExecutor` | explicit compat worker rebuild boundary | Accounted. |
| `TaxOffsetDerivedLifecycleExecutor` | explicit lifecycle boundary | Accounted. |
| `Application.rebuild_tax_offset_read_model_scope(...)` | compat-only thin delegate | Accounted. |
| `Application._schedule_tax_offset_cache_warmup(...)` | app-owned implementation gap | Must be extracted or explicitly quarantined in a narrow follow-up slice. |
| `Application._run_tax_offset_cache_warmup_job(...)` | app-owned implementation gap | Must be extracted or explicitly quarantined in a narrow follow-up slice. |
| Go/Fiber/Go Worker candidates | blocked-by-prerequisite | Not selectable while this local gap remains. |

## Decision

Do not move `tax_offset` local support to `production-evidence-deferred` in this slice.

Close this boundary as analysis/accounting only and insert exactly one next narrow implementation boundary before Go candidates:

`read-models:tax-offset-cache-warmup-executor-port-extraction`

The next slice should:

- move tax offset optional cache warmup scheduling/job execution out of `Application` into an explicit executor/service boundary, or prove and document a stricter compat-only quarantine;
- keep `Application` as dependency assembly and thin delegate/callback provider only;
- preserve env gating, idempotency key shape, job type/label/visibility/source/affected scopes, progress/success/partial-success result shape, read model snapshot persistence operation name, payload build behavior and read model scope behavior;
- add executor/service tests and static guards;
- avoid tax business/API/UI/worker event/queue/schema/Redis contract changes;
- keep Go/Fiber/Go Worker admission blocked.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/tax-offset/state-machine.md`

No global or module state definition changed. This slice changes execution accounting and next-boundary selection only.

Transition:

- Previous queue item: `read-models:tax-offset-post-derived-local-implementation-closure-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Inserted next queue item: `read-models:tax-offset-cache-warmup-executor-port-extraction`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not applicable. This audit did not change tax math, certification, identity, plan selection or source-version business rules. |
| 2. Service-layer tests | Not changed in this slice. Next implementation must add executor/service tests for cache warmup scheduling and job execution contracts. |
| 3. API contract tests | Not applicable. No HTTP/API shape changed. Existing tax offset API tests remain the protection for the next slice. |
| 4. Read model/cache/background job tests | Applicable for the next boundary. This audit found app-owned cache warmup job behavior that needs explicit boundary tests. |
| 5. Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for analysis-only accounting. Real worker/cache warmup drain remains production evidence/defer scope after local gaps close. |
| 7. Existing feature regression tests | Covered by static/docs review only in this slice. Next implementation must preserve tax offset API/runtime/read model regressions. |

## Verification

Expected for this analysis/accounting slice:

```bash
bash scripts/verify.sh docs
git diff --check
```

No production SSH, production DB, staging DB, `PGSQL_URL`, queue mutation or worker replay is required or used for this slice.

## Completion Claim

This slice closes only the post-derived local implementation closure audit. It does not close `tax_offset`, does not move production evidence to deferred, does not unblock Go admission, and does not claim module closure. A local app-owned cache warmup executor gap remains and must be handled next.
