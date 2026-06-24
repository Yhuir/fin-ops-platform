# Read Model Tax Offset Full-State Read Model Snapshot Quarantine

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-full-state-read-model-snapshot-quarantine`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

The final local closure audit found that `Application._persist_state(...)` still serialized `tax_offset_read_models` into the broad full-state snapshot. That preserved an old app-owned read model snapshot write path alongside the explicit runtime/executor read model persistence boundary.

## Selected Boundary

Remove the broad full-state `tax_offset_read_models` write from `Application._persist_state(...)` while preserving explicit tax offset read model persistence through runtime/executor dependencies.

## Implementation Evidence

Updated `backend/src/fin_ops_platform/app/server.py`:

- Removed the `tax_offset_snapshot = self._tax_offset_read_model_service.snapshot()` block from `_persist_state(...)`.
- Removed `"tax_offset_read_models": tax_offset_snapshot` from the broad state-store save payload.
- Left `_persist_tax_offset_read_models_best_effort(...)` intact as the explicit persistence callback used by `TaxOffsetRuntimeService`, `TaxOffsetWorkerRebuildExecutor` and `TaxOffsetCacheWarmupExecutor`.
- Left `TaxOffsetReadModelService.from_snapshot(persisted_state.get("tax_offset_read_models"))` intact as compatibility bootstrap for existing local/Mongo snapshots.

Updated `tests/test_read_model_architecture_guards.py`:

- Added `test_tax_offset_read_models_are_not_written_by_broad_full_state_persist`.
- The guard proves `_persist_state(...)` does not contain `tax_offset_read_models` or `_tax_offset_read_model_service.snapshot()`.
- The guard also proves the explicit `_persist_tax_offset_read_models_best_effort(...)` callback still exists.

## Legacy / Pollution Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `_persist_state(...)` tax offset read model snapshot write | removed | Static guard forbids `tax_offset_read_models` in `_persist_state(...)`. |
| `_persist_tax_offset_read_models_best_effort(...)` | explicit persistence boundary | Retained as injected dependency for runtime/executor-owned read model writes. |
| `TaxOffsetReadModelService.from_snapshot(...)` bootstrap | compat load path | Retained for local/Mongo compatibility; no longer replenished by broad full-state writes. |

## State Machine Impact

- `read-models:tax-offset-full-state-read-model-snapshot-quarantine` transitions to `implementation-closed`.
- `tax_offset` remains `implementation-gap-open` until a post-quarantine local closure audit confirms no other local implementation gaps remain.
- Insert next boundary: `read-models:tax-offset-post-full-state-local-implementation-closure-audit`.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- State-machine definitions do not change; this uses existing `implementation-closed` semantics.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No tax amount, certification, plan or permission rule changed. |
| 2. Service-layer tests | Regression applicable | Static guard protects the service/application boundary; explicit persistence callback remains. |
| 3. API contract tests | Not applicable | No API shape or HTTP behavior changed. |
| 4. Read model/cache/background job tests | Applicable | Guard verifies a broad read model snapshot write path is removed; executor/read model tests remain existing coverage. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this narrow slice | No runtime flow changed outside persistence ownership. |
| 7. Existing feature regression tests | Applicable | Static guard prevents the old full-state snapshot writer from returning. |

## Verification

Initial targeted verification passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_read_model_architecture_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_tax_offset_read_models_are_not_written_by_broad_full_state_persist tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_tax_offset_cache_warmup_is_explicit_executor_boundary -v
```

Final slice verification must also run app check/docs/diff checks before commit.

## Next Boundary

`read-models:tax-offset-post-full-state-local-implementation-closure-audit`

The next audit should re-run local closure after the broad full-state tax offset snapshot write has been removed. If no local gaps remain, it may defer only real PostgreSQL/worker/App Status/high-row/browser evidence without claiming global module closure.
