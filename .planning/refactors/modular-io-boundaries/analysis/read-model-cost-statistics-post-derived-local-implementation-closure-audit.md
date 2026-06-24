# Read Model Cost Statistics Post-Derived Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:cost-statistics-post-derived-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

`cost_statistics` has completed:

- repository port extraction;
- freshness/barrier audit;
- derived lifecycle executor extraction.

`CostStatisticsDerivedLifecycleExecutor` now owns derived lifecycle invalidation, `pending_invoice_rules_changed` persist-empty behavior, no-warmup refresh fallback metadata and `enqueued_jobs` accounting. `Application._derived_lifecycle_cost_statistics_executor(...)` is removed and guarded.

The module is still not globally closed. This audit re-checks local implementation gaps before any Go summary-rollup admission.

## Selected Boundary

Re-audit cost statistics local implementation closure after derived lifecycle executor extraction. If a concrete local implementation gap exists, insert the next narrow implementation boundary before Go candidates.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-cost-statistics-derived-lifecycle-executor-port-extraction.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/cost-statistics/README.md`
- `docs/modules/cost-statistics/implementation-notes.md`
- `docs/modules/cost-statistics/state-machine.md`
- `docs/modules/cost-statistics/tests.md`
- CodeGraph context/explore for cost statistics runtime, derived lifecycle executor, app wrappers and SQL projection owner.
- Focused source review of `server.py`, `cost_statistics_runtime_service.py`, `runtime_worker_registry.py`, `read_model_manifest.py`, `app_status_read_model_registry.py`, `postgres_state_store.py` and relevant tests.

## Audit Findings

| Area | Evidence | Decision |
| --- | --- | --- |
| Derived lifecycle | `CostStatisticsDerivedLifecycleExecutor` owns scope extraction, runtime invalidation, `pending_invoice_rules_changed` persist-empty behavior, no-warmup refresh fallback metadata and `enqueued_jobs` accounting. `Application._derived_lifecycle_cost_statistics_executor(...)` is absent and guarded. | Locally supported. |
| Warmup/retry wrappers | `Application._schedule_cost_statistics_cache_warmup(...)`, `_run_cost_statistics_cache_warmup_job(...)`, retry/recovery/reusable-job helpers, target normalization and summary helpers delegate directly to `CostStatisticsRuntimeService`. `CostStatisticsRuntimeService` owns job creation, progress, read model upsert, explicit persistence and fresh cache writes. | Compat-only app delegates; no new implementation extraction selected in this audit. |
| Worker rebuild wrapper | `Application.rebuild_cost_statistics_read_model_scope(...)` delegates to `CostStatisticsRuntimeService.rebuild_read_model_scope(scope_key)`. Runtime service owns payload load, upsert, explicit persistence and fresh cache write. SQL worker path continues to use `CostStatisticsSqlProjectionBuilder`. | Compat-only app delegate; no local app-owned rebuild gap found. |
| Repository/query/projection | `CostStatisticsReadModelRepositoryPort` owns manifest-listed load/get/save, query service uses SQL fresh gate, and SQL projection saves through the port. | Locally supported. |
| Primary/compat workers | `read_model_manifest.py` and `app_status_read_model_registry.py` identify `cost-statistics` as primary; `runtime_worker_registry.py` keeps `cost-tax` as auxiliary compatibility lane. | Compat-only lane remains; not a local blocker. |
| Direct dirty/outbox writes | Non-transactional refresh enqueue remains through `ReadModelRefreshGateway` via runtime/generic refresh callbacks. No touched business service directly writes `job.outbox_events` or `job.read_model_dirty_scopes` in this audit. | Locally supported. |
| Broad full-state snapshot | `Application._persist_state(...)` still serializes `cost_statistics_read_models` through `self._cost_statistics_read_model_service.snapshot()` into the broad legacy state payload. This mirrors the prior tax offset full-state gap and bypasses the explicit runtime/repository persistence boundary during broad app snapshot saves. | Local implementation gap. Quarantine next. |

## Next Implementation Boundary

`read-models:cost-statistics-full-state-read-model-snapshot-quarantine`

Expected scope:

- Remove broad `Application._persist_state(...)` writes of `cost_statistics_read_models`.
- Keep explicit `CostStatisticsRuntimeService` / query service persistence through `_persist_cost_statistics_read_models_best_effort(...)`.
- Add/update a static architecture guard preventing broad full-state persistence of `cost_statistics_read_models` from returning.
- Preserve `Application` startup load of existing persisted cost statistics read models for local compatibility unless the selected implementation proves it can be safely removed.
- Do not change API, worker, Redis, queue, read model scope, parent aggregate or cost attribution behavior.

## Legacy / Pollution Classification

| Surface | Classification | Owner | Deletion / follow-up condition | Forbidden writes |
| --- | --- | --- | --- | --- |
| `Application._persist_state(...)` writing `cost_statistics_read_models` | local implementation gap | currently broad app full-state snapshot | next boundary | Must not serialize cost statistics read models as part of broad app snapshot persistence. |
| `_persist_cost_statistics_read_models_best_effort(...)` | explicit persistence boundary | `CostStatisticsRuntimeService` / query service callbacks | keep | Must remain the explicit read model persistence callback until a narrower repository owner replaces it. |
| `Application._schedule_cost_statistics_cache_warmup(...)` | compat-only delegate | `CostStatisticsRuntimeService` | reassess after full-state quarantine if needed | Must not create jobs or upsert read models outside runtime service. |
| `Application._run_cost_statistics_cache_warmup_job(...)` | compat-only delegate | `CostStatisticsRuntimeService` | reassess after full-state quarantine if needed | Must not upsert read models or cache payloads outside runtime service. |
| `Application.rebuild_cost_statistics_read_model_scope(...)` | worker compat delegate | `CostStatisticsRuntimeService` | keep until worker API/runtime split changes | Must not rebuild, persist or cache directly in `Application`. |
| `cost-tax` worker lane | compatibility lane | `runtime_worker_registry.py` auxiliary worker | retire only under a separate worker migration/admission plan | Must not become primary cost statistics owner. |

## State Machine Impact

- `read-models:cost-statistics-post-derived-local-implementation-closure-audit` transitions to `analysis-closed`.
- `cost_statistics` remains `implementation-gap-open`.
- Insert `read-models:cost-statistics-full-state-read-model-snapshot-quarantine` as the next pending boundary before Go candidates.
- Go/Fiber/Go Worker candidates remain `blocked-by-prerequisite`.
- Global state-machine definitions do not change; this uses existing `analysis-closed` semantics.
- `docs/modules/cost-statistics/state-machine.md` definitions do not change; the audit identifies implementation ownership cleanup only.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable for this audit | No cost attribution, project scope, amount, relation eligibility, permission or export business rule changed. |
| 2. Service-layer tests | Applicable as evidence | Existing executor/runtime/query tests prove current service ownership; next implementation must add/update a static guard for broad full-state persistence. |
| 3. API contract tests | Existing regression applies | No HTTP behavior changed. |
| 4. Read model/cache/background job tests | Applicable | Existing cost statistics runtime/SQL tests cover explicit persistence, warmup/rebuild and fresh gate behavior. |
| 5. Frontend component and interaction tests | Not applicable for this audit | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this audit | No runtime business flow changed. |
| 7. Existing feature regression tests | Applicable | Re-run targeted cost statistics runtime/SQL/executor tests and architecture guards before commit. |

## Verification

Required for this analysis/accounting slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_cost_statistics_derived_lifecycle_executor tests.test_cost_statistics_runtime_service tests.test_cost_statistics_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_cost_statistics_derived_lifecycle_uses_explicit_executor_boundary tests.test_read_model_architecture_guards -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

Known unrelated broad guard failures remain outside this slice:

- `backend/src/fin_ops_platform/tools/repair_submitted_etc_invoice_overlaps.py` contains direct `update app.invoices` SQL.
- `backend/src/fin_ops_platform/tools/oa_attachment_invoice_promotion.py` passes `allow_create` to OA attachment invoice upsert, and the existing server promotion guard does not find the expected `CREATE_INVOICE_AND_LINK` expression.

## Next Boundary

`read-models:cost-statistics-full-state-read-model-snapshot-quarantine`
