# Read Model Turnover Ledger Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:turnover-ledger-local-implementation-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Previous State

`turnover_ledger` had three completed local slices:

- repository port extraction: `TurnoverLedgerReadModelRepositoryPort` owns only `list_turnover_ledger_view`, `save_turnover_ledger_rows` and `clear_turnover_ledger_rows`;
- freshness/barrier audit: SQL fresh gate, month/all scope policy, manifest/App Status/worker registration, Workbench relation source-version proof and operation barrier evidence were accounted for;
- refresh producer/clear extraction: non-transactional refresh and best-effort clear moved from app-owned helpers into `TurnoverLedgerReadModelRefreshProducer`.

This audit rechecked remaining local implementation surfaces before moving the module out of `implementation-gap-open`.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-refresh-freshness-operation-barrier-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-turnover-ledger-refresh-producer-clear-port-extraction.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/turnover-ledger/README.md`
- `docs/modules/turnover-ledger/implementation-notes.md`
- `docs/modules/turnover-ledger/tests.md`
- `docs/modules/turnover-ledger/state-machine.md`
- `docs/dev/api-contracts.md`
- `docs/operations/runtime-worker-governance.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_turnover_ledger.py`
- `backend/src/fin_ops_platform/app/turnover_ledger_read_facade.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_read_model_repository.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh_producer.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_query_service.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_sql_projection.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_facade.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_uow.py`
- `backend/src/fin_ops_platform/services/bank_details_application_service.py`
- `web/src/pages/TurnoverLedgerPage.tsx`
- `web/src/features/turnoverLedger/api.ts`
- `tests/test_turnover_ledger_read_model_refresh_producer.py`
- `tests/test_turnover_ledger_query_service.py`
- `tests/test_turnover_ledger_read_model_refresh.py`
- `tests/test_turnover_ledger_api.py`
- `tests/test_read_model_architecture_guards.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_operation_freshness_barrier.py`
- `tests/test_read_model_manifest.py`
- `tests/test_runtime_worker_registry.py`

## CodeGraph Evidence

CodeGraph status was healthy. `codegraph_context` and `codegraph_explore` over the turnover read model/write/query/worker symbols found:

- `TurnoverLedgerQueryService` reads through `ReadModelQueryGateway` for `turnover_ledger:all` and falls back to legacy payload only when PostgreSQL SQL read model runtime is not required.
- `TurnoverLedgerReadModelRefreshService` only handles `turnover_ledger.read_model.refresh`, delegates rebuild to the projection builder and completes the dirty scope through the queue repository.
- `TurnoverLedgerSqlProjectionBuilder` saves through `save_turnover_ledger_rows` on the injected read repository and fails if the method is absent.
- `TurnoverLedgerWriteUnitOfWork` writes transactional dirty/outbox requests through the injected dirty outbox writer, not through app-owned job SQL.
- `TurnoverLedgerDirtyOutboxWriter` normalizes scopes through `ReadModelScopePolicyRegistry` before calling `enqueue_read_model_refresh_in_transaction`.
- `Application` remains dependency assembly for turnover route/facade factories and no longer owns the removed refresh/clear helper methods.

## Local Surface Classification

| Surface | Classification | Evidence |
| --- | --- | --- |
| `TurnoverLedgerQueryService` | explicit read boundary | Uses `ReadModelQueryGateway`, expected source versions and empty refreshing payload; no direct dirty/outbox/readiness/cache writes. |
| `TurnoverLedgerReadModelRepositoryPort` | explicit repository port | Manifest-listed methods only; port guard prevents unrelated read model methods from leaking into turnover. |
| `TurnoverLedgerSqlProjectionBuilder` | explicit projection builder | Projection save path uses `save_turnover_ledger_rows`; Workbench relation non-fresh behavior is already guarded from saving partial rows. |
| `TurnoverLedgerReadModelRefreshProducer` | explicit non-transactional refresh/clear boundary | Enqueue stays behind `ReadModelRefreshGateway`; clear uses turnover-specific port. |
| `TurnoverLedgerReadModelRefreshService` | explicit worker handler | Handles only `turnover_ledger.read_model.refresh`; completes dirty scope via queue repository. |
| `TurnoverLedgerWriteFacade` / `TurnoverLedgerWriteUnitOfWork` | explicit transactional write boundary | Transactional refresh requests go through injected dirty outbox writer and equivalent scope policy. |
| `TurnoverLedgerDirtyOutboxWriter` | explicit transactional queue port | Uses `enqueue_read_model_refresh_in_transaction` after scope policy normalize/validate. |
| `TurnoverLedgerLocalDirtyOutboxWriter` | compat-only local adapter | Local/non-Postgres path delegates to `ReadModelRefreshGateway.enqueue_many_events`; no direct job SQL/readiness/cache writes. |
| turnover legacy fallback facades | compat-only fallback | Still support local/non-Postgres compatibility, but read model side effects now delegate to producer or UoW adapters. |
| `BankDetailsApplicationService._enqueue_turnover_ledger_read_model_refreshes(...)` | compat-only service fallback | Normal server factory injects `TurnoverLedgerReadModelRefreshProducer.enqueue`; the internal fallback is retained for isolated/local construction and still uses `ReadModelRefreshGateway`, not direct SQL/job table writes. |
| frontend turnover write flows | explicit operation barrier consumer | Tag-selection, extra save, confirm and withdraw wait on `turnover_ledger` operation barrier targets before reload. |
| manifest / App Status / worker registry | explicit runtime contract | `turnover_ledger` is registered in manifest, App Status read model/job/domain registry and runtime worker registry. |

## Legacy And Boundary Decision

No remaining local implementation gap was found after the refresh producer/clear extraction.

Removed:

- `Application._enqueue_turnover_ledger_read_model_refreshes(...)`
- `Application._clear_turnover_ledger_read_model_best_effort(...)`

Quarantined as compat-only:

- turnover legacy fallback facades;
- `TurnoverLedgerLocalDirtyOutboxWriter`;
- `BankDetailsApplicationService._enqueue_turnover_ledger_read_model_refreshes(...)` fallback branch when no explicit producer callback is injected.

Forbidden writes for compat-only surfaces:

- no direct writes to `job.outbox_events`;
- no direct writes to `job.read_model_dirty_scopes`;
- no direct writes to App Status readiness;
- no direct Redis fresh payload publishing;
- no replacement of `ReadModelRefreshGateway`, `ReadModelQueryGateway`, `TurnoverLedgerReadModelRepositoryPort` or transactional dirty outbox writer contracts.

## Production Evidence Deferred

The following evidence is still unavailable locally and is explicitly deferred:

- real PostgreSQL `turnover_ledger` read model rows/source versions/readiness proof;
- real worker drain for `turnover_ledger.read_model.refresh`;
- real dirty/outbox/readiness/App Status state after turnover writes;
- high-row grouped ledger performance evidence;
- authenticated browser smoke against production data;
- write-operation SLO proof for real turnover tag-selection/extra/confirm/withdraw operations.

This defer status does not mean the `turnover_ledger` module is globally closed.

## Seven-Category Test Decision

1. Business core unit tests: not applicable; no turnover amount, grouping, closure, withdraw, tag or extra rule changed.
2. Service-layer tests: applicable by evidence; existing UoW, producer, query service, worker and platform boundary tests cover the audited service boundaries.
3. API contract tests: applicable by regression evidence; existing turnover API tests cover response shape, freshness targets, idempotency and queue behavior. No API shape changed in this audit.
4. Read model/cache/background job tests: applicable by evidence; turnover query/refresh/producer tests, manifest tests, runtime worker registry and operation barrier tests cover local contracts.
5. Frontend component and interaction tests: applicable by evidence only; no frontend code changed, but existing turnover page/API tests cover operation barrier and stale grouped payload behavior.
6. End-to-end business-flow integration tests: applicable by evidence only; existing turnover/workbench integration and browser E2E docs cover confirm/withdraw/tag-selection flows. No new E2E was added for analysis-only work.
7. Existing feature regression tests: applicable by evidence; platform/runtime boundary guards and turnover regressions protect old helper removal and read model refresh behavior.

## State Impact

- Queue item `144` moves from `pending` to `production-evidence-deferred`.
- `turnover_ledger` moves from `implementation-gap-open` to `not-module-closed`.
- Insert next boundary: `read-models:next-pilot-selection-after-turnover-ledger`.
- Go/Fiber/Go Worker admission remains blocked because `no_oa_bank_batch`, `search` and `bank_account_balance` have not been selected/audited as non-Go read model pilots.
- State-machine definitions are unchanged; this slice updates progress/accounting only.

## Verification

Verification run for this analysis/accounting slice:

- `PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check` passed.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_turnover_ledger_read_model_refresh_producer tests.test_turnover_ledger_query_service tests.test_turnover_ledger_read_model_refresh -v` passed.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry tests.test_operation_freshness_barrier -v` passed.
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_bank_details_auto_tag_and_category_writes_stay_on_application_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_read_model_refresh_producers_use_scope_gateway_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_business_code_does_not_write_outbox_or_dirty_scopes_directly tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_runtime_worker_entrypoint_does_not_import_application -v` passed.
- `bash scripts/verify.sh docs` passed.
- `git diff --check` passed.

Known unrelated verification failure:

- Full `tests.test_platform_runtime_boundary_guards` currently fails on OA/invoice guard items unrelated to this turnover/read model accounting slice:
  - `backend/src/fin_ops_platform/tools/repair_submitted_etc_invoice_overlaps.py` contains direct `update app.invoices` SQL;
  - `backend/src/fin_ops_platform/tools/oa_attachment_invoice_promotion.py` passes `allow_create` to OA attachment invoice upsert;
  - `server.py` OA attachment promotion does not gate `allow_create` on `CREATE_INVOICE_AND_LINK`.
  These files were not changed by this slice and remain a separate boundary/bugfix candidate.

## Next Boundary

`read-models:next-pilot-selection-after-turnover-ledger`
