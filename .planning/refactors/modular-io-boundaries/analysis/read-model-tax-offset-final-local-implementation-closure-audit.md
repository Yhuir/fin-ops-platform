# Read Model Tax Offset Final Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-final-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`tax_offset` had completed these local modular IO slices:

- repository port extraction;
- freshness / operation barrier audit;
- worker rebuild executor extraction;
- derived lifecycle executor extraction;
- cache warmup executor extraction.

The queue required a final local implementation closure audit before `tax_offset` could move to `production-evidence-deferred`.

## Selected Boundary

Re-audit local `tax_offset` implementation support after cache warmup extraction and decide whether only real environment evidence remains, or whether another local implementation gap still blocks defer.

## Evidence Inspected

CodeGraph and literal scans inspected:

- `Application._configure_tax_offset_application_services(...)`;
- tax offset API route wrappers and session resolution;
- `TaxOffsetQueryService`, `TaxOffsetRuntimeService`, `TaxOffsetWorkerRebuildExecutor`, `TaxOffsetDerivedLifecycleExecutor`, `TaxOffsetCacheWarmupExecutor`;
- `Application.rebuild_tax_offset_read_model_scope(...)`;
- `Application._schedule_tax_offset_cache_warmup(...)`;
- derived lifecycle registry entries for `tax_offset_read_model` and `tax_offset_month_cache`;
- `Application._persist_state(...)`;
- manifest/scope policy/worker/App Status registry entries;
- tax offset executor/API/runtime/static guard tests.

## Accounted Local Support

| Area | Status | Evidence |
| --- | --- | --- |
| Repository port | Accounted | `TaxOffsetReadModelRepositoryPort` exposes manifest-listed load/get/save only; state-store read/write and projection save paths use the port. |
| Fresh gate | Accounted | SQL reads use `ReadModelQueryGateway`; production SQL repository miss/unavailable fails closed as refreshing/enqueue. |
| Force refresh / scope policy | Accounted | `tax_offset` uses month/all scope policy; `all` fans out to month shards. |
| Operation barrier | Accounted | Plan save/certified import frontend waits on current-month `tax_offset` target; backend exposes freshness targets. |
| Worker rebuild | Accounted | `TaxOffsetWorkerRebuildExecutor` owns rebuild, upsert, persistence callback and fresh Redis cache publish. |
| Derived lifecycle | Accounted | `TaxOffsetDerivedLifecycleExecutor` owns read model invalidation and month-cache clearing; registry uses explicit executor methods. |
| Cache warmup | Accounted | `TaxOffsetCacheWarmupExecutor` owns env gate, job scheduling/execution, upsert and snapshot persistence. |
| App route wrappers | Accounted | Remaining app route methods are session/auth resolution and route delegation. |
| App runtime wrappers | Accounted | Remaining runtime wrappers delegate to `TaxOffsetRuntimeService` / `TaxOffsetQueryService`; static guards cover the heavy worker/cache-warm paths. |
| Manifest/worker/App Status | Accounted locally | `read_model_manifest.py`, runtime worker registry and App Status job/domain registries include tax offset contracts. |

## Remaining Local Implementation Gap

`Application._persist_state(...)` still serializes `tax_offset_read_models` into the broad full-state snapshot:

```python
tax_offset_snapshot = (
    self._tax_offset_read_model_service.snapshot()
    if self._tax_offset_read_model_service is not None
    else {}
)
...
"tax_offset_read_models": tax_offset_snapshot,
```

This is still an app-owned legacy full-state write path for a read model snapshot. It is separate from the explicit read model persistence callback used by tax offset runtime/executor boundaries, and it can preserve the old broad state-save chain as a second writer for read model data.

Because the refactor requirement says old paths must not write authoritative derived/read model outputs into the new chain, `tax_offset` cannot move to `production-evidence-deferred` yet.

## Legacy / Pollution Classification

| Surface | Classification | Decision |
| --- | --- | --- |
| `Application._persist_state(...)` writing `tax_offset_read_models` | app-owned legacy snapshot gap | Must be removed or quarantined in the next implementation slice. |
| `Application._persist_tax_offset_read_models_best_effort(...)` | explicit persistence callback | Can remain for now as injected dependency used by runtime/executor boundaries; next slice should ensure it remains the only local state-store snapshot write path. |
| `TaxOffsetReadModelService.from_snapshot(...)` bootstrap | compat load path | May remain as compatibility while local/Mongo runtime exists, but must not be refreshed by broad `_persist_state(...)`. |
| `Application._schedule_tax_offset_cache_warmup(...)` | compat-only thin delegate | Already guarded. |
| `Application.rebuild_tax_offset_read_model_scope(...)` | compat-only thin delegate | Already guarded. |

## State Machine Impact

- `read-models:tax-offset-final-local-implementation-closure-audit` is `analysis-closed`.
- `tax_offset` remains `implementation-gap-open`.
- Insert next boundary: `read-models:tax-offset-full-state-read-model-snapshot-quarantine`.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- State-machine definitions do not change; this uses existing `analysis-closed` and `implementation-gap-open` semantics.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rule changed in this audit slice. |
| 2. Service-layer tests | Not applicable for analysis | Next implementation slice should add/update a guard around broad `_persist_state(...)` tax offset snapshot writes. |
| 3. API contract tests | Not applicable | No API behavior changed. |
| 4. Read model/cache/background job tests | Applicable to next slice | The identified gap is a legacy read model snapshot write path; next implementation must guard it. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for analysis | No runtime flow changed. |
| 7. Existing feature regression tests | Applicable to next slice | Existing tax offset cache/rebuild/derived lifecycle guards must remain green after quarantine. |

## Verification

This slice is analysis/accounting only. Verification should include docs verification and diff checks after state/doc updates.

## Next Boundary

`read-models:tax-offset-full-state-read-model-snapshot-quarantine`

The next implementation slice should remove or quarantine the broad `_persist_state(...)` tax offset read model snapshot write while preserving explicit tax offset read model persistence through runtime/executor boundaries and maintaining local compatibility where required.
