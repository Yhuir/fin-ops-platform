# Read Model Cost Statistics Full-State Read Model Snapshot Quarantine

**Date:** 2026-06-24
**Boundary:** `read-models:cost-statistics-full-state-read-model-snapshot-quarantine`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`read-models:cost-statistics-post-derived-local-implementation-closure-audit` found the remaining local implementation gap: broad `Application._persist_state(...)` still serialized `cost_statistics_read_models` through `self._cost_statistics_read_model_service.snapshot()` into the legacy full-state payload.

Warmup/retry/rebuild app methods were already compat-only delegates to `CostStatisticsRuntimeService`, and explicit cost statistics read model persistence already existed through `_persist_cost_statistics_read_models_best_effort(...)`.

## Selected Boundary

Remove broad full-state snapshot writes of cost statistics read models while preserving explicit runtime/query persistence and startup compatibility.

## Implementation

Updated `backend/src/fin_ops_platform/app/server.py`:

- Removed `cost_statistics_snapshot = self._cost_statistics_read_model_service.snapshot()` from `_persist_state(...)`.
- Removed `"cost_statistics_read_models": cost_statistics_snapshot` from the broad state payload.
- Preserved startup loading from `persisted_state.get("cost_statistics_read_models")` for local compatibility.
- Preserved explicit `_persist_cost_statistics_read_models_best_effort(...)` for runtime/query service persistence.

Updated `tests/test_read_model_architecture_guards.py`:

- Renamed and expanded the broad full-state guard to `test_cost_and_tax_read_models_are_not_written_by_broad_full_state_persist`.
- The guard now proves `_persist_state(...)` does not serialize either `cost_statistics_read_models` or `tax_offset_read_models`.
- The guard still requires explicit `_persist_cost_statistics_read_models_best_effort(...)` and `_persist_tax_offset_read_models_best_effort(...)` to exist.

## Preserved Behavior

- No cost attribution, project scope, export behavior, parent aggregate semantics, worker event names, queue schema, Redis key/envelope contract, permissions, audit meaning, API shape or frontend behavior changed.
- Explicit runtime/query persistence remains available.
- Startup can still load existing local cost statistics read model snapshots.
- SQL/PostgreSQL read model repository port behavior is unchanged.

## Legacy / Pollution Classification

| Surface | Classification | Result |
| --- | --- | --- |
| `Application._persist_state(...)` cost statistics snapshot write | removed old broad full-state write path | No longer serializes `cost_statistics_read_models`. |
| `Application._persist_cost_statistics_read_models_best_effort(...)` | explicit persistence boundary | Preserved. |
| Cost statistics startup `from_snapshot(...)` | local compatibility read path | Preserved in this narrow slice. |
| `Application._schedule_cost_statistics_cache_warmup(...)` / `_run_cost_statistics_cache_warmup_job(...)` | compat-only delegates | Unchanged; still delegate to `CostStatisticsRuntimeService`. |
| `Application.rebuild_cost_statistics_read_model_scope(...)` | worker compat delegate | Unchanged; still delegates to `CostStatisticsRuntimeService`. |

## State Machine Impact

- `read-models:cost-statistics-full-state-read-model-snapshot-quarantine` transitions to `implementation-closed`.
- `cost_statistics` remains `implementation-gap-open` until a post-quarantine local closure audit re-checks current code.
- Insert `read-models:cost-statistics-post-full-state-local-implementation-closure-audit` as the next pending boundary before Go candidates.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `implementation-closed` semantics.
- `docs/modules/cost-statistics/state-machine.md` definitions do not change; this is an implementation ownership cleanup only.

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not applicable. No cost attribution, amount, project scope, permission, relation or export business rule changed. |
| 2. Service-layer tests | Applicable and covered by cost statistics runtime/derived lifecycle tests proving explicit persistence paths still work. |
| 3. API contract tests | Not applicable. No HTTP route or response shape changed. |
| 4. Read model/cache/background job tests | Applicable and covered by cost statistics runtime/SQL tests plus the full-state architecture guard. |
| 5. Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not required for this narrow persistence ownership cleanup. |
| 7. Existing feature regression tests | Applicable and covered by cost statistics runtime/SQL/derived lifecycle tests and architecture guard. |

## Verification

Ran:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_read_model_architecture_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards.ReadModelArchitectureGuardTests.test_cost_and_tax_read_models_are_not_written_by_broad_full_state_persist -v
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_runtime_service tests.test_cost_statistics_derived_lifecycle_executor tests.test_cost_statistics_sql_runtime -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- Real PostgreSQL/worker/App Status/high-row/browser evidence remains unavailable without production validation.
- This slice does not prove full local closure of `cost_statistics`; a post-full-state local implementation closure audit is required next.
- `cost_statistics` is not globally closed.

## Next Boundary

`read-models:cost-statistics-post-full-state-local-implementation-closure-audit`
