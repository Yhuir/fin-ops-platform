# Tax Offset Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:tax-offset-local-implementation-closure-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Previous State

- `TaxOffsetReadModelRepositoryPort` had been extracted and wired through PostgreSQL state-store read/write paths and `TaxOffsetSqlProjectionBuilder` save paths.
- Freshness/barrier audit had accounted for SQL fresh gate, force refresh, `all` fan-out/month proof, operation barrier and the OA attachment invoice `invoice_type` fallback fix.
- The queue asked this slice to decide whether local `tax_offset` implementation support could move to `production-evidence-deferred`.

## Audit Scope

Checked local evidence for:

- repository port;
- query fresh gate;
- force refresh/scope policy;
- `all` fan-out/month shard proof;
- operation barrier;
- worker/manifest/App Status registration;
- source-version proof;
- OA attachment invoice fallback;
- retained legacy/app-owned helper classifications;
- tests/docs.

Sources inspected:

- CodeGraph context/explore for `TaxOffsetQueryService`, `TaxOffsetRuntimeService`, `TaxOffsetReadModelRefreshService`, `TaxOffsetSqlProjectionBuilder`, `TaxOffsetPlanService` and `TaxOffsetReadModelRepositoryPort`;
- `backend/src/fin_ops_platform/app/server.py`;
- `backend/src/fin_ops_platform/services/read_model_manifest.py`;
- `backend/src/fin_ops_platform/services/app_status_read_model_registry.py`;
- `backend/src/fin_ops_platform/services/runtime_worker_registry.py`;
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`;
- `tests/test_read_model_architecture_guards.py`;
- tax offset/read-models module docs and prior modular IO analysis files.

## Accounted Local Evidence

Repository port:

- `TaxOffsetReadModelRepositoryPort` exposes only `load_tax_offset_read_models`, `get_tax_offset_view` and `save_tax_offset_read_models`.
- `PostgresStateStore.tax_offset_sql_read_repository` returns the narrow port.
- `TaxOffsetSqlProjectionBuilder` saves rebuilt scopes through the port.

Fresh gate and source-version proof:

- `TaxOffsetQueryService.get_month_from_sql_read_model(...)` uses `ReadModelQueryGateway.load(...)` with schema/source-version proof and source-versioned Redis keys.
- Production SQL runtime with missing SQL repository returns refreshing/unavailable and enqueues refresh instead of live rebuilding.
- `TaxOffsetPlanService.save_plan(...)` rejects non-fresh read models, scope mismatch and source-version mismatch before writing a plan.

Refresh, scope policy and worker registration:

- `read_model_scope_policy.py` registers `tax_offset` as month-or-all.
- `TaxOffsetReadModelRefreshService` handles only `tax_offset.read_model.refresh`.
- `scope_key == "all"` fans out into concrete month shards through `ReadModelRefreshGateway.enqueue_many(...)` and completes the parent `all` scope without writing an `all` payload.
- `read_model_manifest.py` registers `tax_offset` as `partitioned_scoped_incremental`, `all_scope_semantics=fan_out_command`, `primary_worker_instance="tax-offset"`, and `auxiliary_refresh_worker_instances=("cost-tax",)`.
- `app_status_read_model_registry.py` maps `tax_offset` to worker instance `tax-offset` and event `tax_offset.read_model.refresh`.
- `runtime_worker_registry.py` contains the dedicated `tax-offset` worker and the legacy combined `cost-tax` compatibility worker.

Operation barrier:

- `TaxOffsetPage` waits for `operationBarrierTargets("tax_offset", [currentMonth])` after plan save and certified import completion before reloading.
- Existing tests cover the current-month operation barrier contract.

OA attachment invoice fallback:

- `FinancialObjectIdentityPolicy` now treats `invoice_type=进项发票` / `销项发票` as formal OA attachment invoice evidence when `evidence_type` is missing.
- Explicit receipt/unknown evidence remains excluded.

## Local Implementation Gap Found

`tax_offset` cannot move to `production-evidence-deferred` yet.

Concrete gap:

- `Application.rebuild_tax_offset_read_model_scope(...)` still contains app-owned projection behavior:
  - reads month payload through `self._tax_api_routes.get_tax_offset(month)`;
  - writes the in-memory `TaxOffsetReadModelService`;
  - persists tax offset read model snapshots;
  - writes fresh Redis month and summary cache envelopes.
- This method is still included in `tests/test_read_model_architecture_guards.py` direct-fresh allowlist as a worker rebuild publisher. The allowlist documents why `read_model_status=fresh` appears, but it does not move ownership out of `Application`.
- Production SQL worker uses `TaxOffsetSqlProjectionBuilder`; however the app-owned rebuild path is still a real local implementation surface for non-SQL/compat worker wiring and cache warmup behavior.

Related retained surface:

- `_derived_lifecycle_tax_offset_executor(...)` remains in `Application` and invalidates tax offset read models through app wrappers.
- `_derived_lifecycle_tax_offset_month_cache_executor(...)` remains in `Application` and clears service month cache.
- These may be acceptable compat/support surfaces after the worker rebuild ownership is extracted, but they should be re-audited instead of hidden under a production-evidence defer claim.

Decision:

- Do not mark `read-models:tax-offset-local-implementation-closure-audit` as `production-evidence-deferred`.
- Close this slice as analysis/accounting only.
- Insert the next narrow implementation boundary: `read-models:tax-offset-worker-rebuild-executor-port-extraction`.
- Keep Go/Fiber/Go Worker admission blocked.

## Proposed Next Boundary

`read-models:tax-offset-worker-rebuild-executor-port-extraction`

Scope:

- Move `Application.rebuild_tax_offset_read_model_scope(...)` worker rebuild/persist/cache publish behavior into an explicit tax offset worker rebuild executor or equivalent service/port.
- Keep `Application` as dependency assembly and thin delegate only.
- Preserve payload shape, source-version proof, fresh cache envelope shape, Redis key contract, `entry_count`, and in-memory compatibility behavior.
- Add unit/static guard coverage proving the old app-owned rebuild method no longer returns implementation logic.
- Do not change SQL production projection builder, tax calculation rules, certification import, plan save API shape, worker event names, queue schema, frontend behavior, Go/Fiber or Go Worker.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/tax-offset/state-machine.md`

No state definition changed. This slice changes only execution accounting and next-boundary selection.

Transition:

- Previous queue item: `read-models:tax-offset-local-implementation-closure-audit`
- Previous status: `pending`
- New status: `analysis-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:tax-offset-worker-rebuild-executor-port-extraction`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not applicable. This audit did not change tax math, certification, identity or plan rules. |
| 2. Service-layer tests | Not changed in this slice. Next implementation must add executor/service tests if behavior is moved. |
| 3. API contract tests | Not applicable. No HTTP/API shape changed. |
| 4. Read model/cache/background job tests | Applicable for the next boundary. This audit identified app-owned rebuild/cache publish behavior that needs executor-level tests. |
| 5. Frontend component and interaction tests | Not applicable. No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for analysis-only accounting. Real worker drain remains production evidence/defer scope after local gaps are closed. |
| 7. Existing feature regression tests | Covered by docs/static inventory only in this slice; next implementation must preserve existing tax offset SQL/runtime/API regressions. |

## Verification

```bash
git status --short --branch
git fetch --prune origin
git pull --ff-only origin dev
git merge --no-edit origin/main
```

The fetch/pull/merge preflight reported `Already up to date` for `origin/dev` and `origin/main`.

```bash
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

This slice closes only local implementation closure accounting for `tax_offset`. It intentionally does not close `tax_offset`, defer production evidence, or unblock Go admission because a local app-owned worker rebuild executor gap remains.
