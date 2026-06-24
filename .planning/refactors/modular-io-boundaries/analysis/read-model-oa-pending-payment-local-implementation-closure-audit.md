# Read Model OA Pending Payment Local Implementation Closure Audit

**Date:** 2026-06-24
**Boundary:** `read-models:oa-pending-payment-local-implementation-closure-audit`
**Slice status:** `production-evidence-deferred`
**Module closure:** `not-module-closed`

## Goal

Audit whether the `oa_pending_payment` read model pilot has remaining local non-Go implementation gaps after repository port extraction and freshness/operation-barrier work. If a narrow legacy path remains, remove or quarantine it before any Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-repository-port-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-oa-pending-payment-refresh-freshness-operation-barrier-audit.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/oa-pending-payments/tests.md`
- `docs/modules/oa-pending-payments/state-machine.md`
- `docs/modules/oa-pending-payments/implementation-notes.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_repository.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/read_model_scope_policy.py`
- `backend/src/fin_ops_platform/services/read_model_refresh_gateway.py`
- `backend/src/fin_ops_platform/services/operation_freshness_barrier.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `web/src/pages/OaPendingPaymentsPage.tsx`
- `web/src/test/OaPendingPaymentsPage.test.tsx`
- `tests/test_oa_pending_payment_api.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`
- `tests/test_read_model_manifest.py`
- `tests/test_read_model_architecture_guards.py`
- `tests/test_write_operation_slo_audit.py`

CodeGraph was used before editing to inspect the remaining OA pending payment symbols and callers. `rebuild_oa_pending_payment_read_model_scope` and `list_oa_pending_payment_scope_shards` had no runtime callers outside the worker projection builder and tests; the `Application` methods were only covered by a legacy test.

## Local Closure Accounting

| Requirement | Evidence | Local status |
| --- | --- | --- |
| Narrow read-model repository port | `OaPendingPaymentReadModelRepositoryPort` exposes only OA pending payment read/model methods and is wired into PostgreSQL state store, API read service and worker projection save/mark/prune paths. | Accounted |
| Query fresh gate | `OaPendingPaymentReadModelService` returns `refreshing` on missing repository/payload, stale refresh status or source-version mismatch and enqueues through `ReadModelRefreshGateway`. | Accounted |
| Source-version proof | Base OA pending payment versions are combined with Workbench relation scope versions through the Workbench relation port; default `all` does not depend on global relation `all`. | Accounted |
| Scope policy and force refresh | `ReadModelScopePolicyRegistry` accepts only month or `all` for `oa_pending_payment`; non-transactional refresh enqueue goes through `ReadModelRefreshGateway`. | Accounted |
| Worker fan-out | `InvoiceUsageCollectionReadModelRefreshService` expands fan-out `all` through `InvoiceUsageCollectionSqlProjectionBuilder.list_oa_pending_payment_scope_shards(...)`, prunes orphan shards, enqueues month shards and skips stale source-version events. | Accounted |
| Projection write boundary | Worker rebuild uses `InvoiceUsageCollectionSqlProjectionBuilder.rebuild_oa_pending_payment_read_model_scope(...)` and writes rows/scope readiness through `OaPendingPaymentReadModelRepositoryPort`. | Accounted |
| Operation barrier after writes | Auto-reconcile and bank-link frontend flows wait on concrete month barrier targets when backend responses include concrete scopes plus `all`; `all` remains fallback only. | Accounted |
| Legacy contamination | The unused `Application` OA pending payment rebuild/list/mark/live helper path has been removed. New tests prevent it from returning. | Accounted |
| Tests/docs | Backend API/read model/projection tests, frontend barrier tests, module docs and GSD analysis files are recorded and updated. | Accounted |

## Implementation

Removed the unused app-level OA pending payment read model rebuild path:

- `Application.list_oa_pending_payment_scope_shards(...)`
- `Application.mark_oa_pending_payment_scope_empty(...)`
- `Application.rebuild_oa_pending_payment_read_model_scope(...)`
- `Application._oa_pending_payment_live_rows(...)`
- `Application._oa_pending_payment_live_rows_for_view(...)`

The retained worker path is the explicit projection builder:

- `InvoiceUsageCollectionReadModelRefreshService`
- `InvoiceUsageCollectionSqlProjectionBuilder`
- `OaPendingPaymentReadModelRepositoryPort`

`tests/test_oa_pending_payment_api.py` now has a regression guard proving the removed `Application` helpers cannot return.

## Retained Surfaces

| Surface | Classification | Reason |
| --- | --- | --- |
| `Application._oa_pending_payment_service(...)` | route/service dependency assembly | It builds `OaPendingPaymentQueryService` with explicit dependencies; no SQL read-model write or job queue write happens here. |
| `Application._oa_pending_payment_command_service(...)` | command-service dependency assembly | It injects explicit Workbench refresh and OA pending payment refresh callbacks into the command service; command semantics are unchanged. |
| `Application._enqueue_oa_pending_payment_read_model_refresh(...)` | gateway-backed producer wrapper | It delegates to `ReadModelRefreshGateway.enqueue_one("oa_pending_payment", ...)`; it does not direct-SQL write dirty scopes or outbox. |
| `Application._oa_pending_payment_expected_source_versions(...)` | source-version provider | It composes OA source versions with Workbench relation versions from the Workbench relation port. |
| `Application._handle_api_oa_pending_payments_*` | HTTP mapping | These methods perform auth/body/error/response mapping and delegate to `OaPendingPaymentApiRoutes`. |
| `InvoiceUsageCollectionSqlProjectionBuilder.list_oa_pending_payment_scope_shards(...)` | retained source-fact enumeration | It enumerates completed OA projection months plus payment-admitted in-progress months for fan-out. This is the worker builder, not a legacy app path. |

## Production Evidence Deferred

The autonomous plan must not depend on local `PGSQL_URL` or a staging database and must not perform production writes without explicit approval. Therefore this slice cannot prove real production evidence for:

- production `job.outbox_events` / `job.read_model_dirty_scopes` enqueue-to-done for `oa_pending_payment`;
- current-effective `read_model.app_status_readiness` for OA pending payment scopes;
- real `invoice-usage-collection` worker drain for OA fan-out and month shards;
- production App Status evidence for `oa_pending_payments`;
- high-row OA pending payment API p95/p99 against production-sized data;
- authenticated browser smoke after a real OA pending payment write.

This is a soft gate. It prevents global module closure, but it does not block the next local modular IO pilot.

## Decision

The last local legacy implementation gap found in this audit was removed. No additional local non-Go OA pending payment implementation gap was found.

Set:

- `read-models:oa-pending-payment-local-implementation-closure-audit`: `production-evidence-deferred`
- module closure: `not-module-closed`
- Go hot-path admission: still `blocked-by-prerequisite`

Insert the next executable boundary before Go candidates:

- `read-models:next-pilot-selection-after-oa-pending-payment`

The next boundary should compare remaining read model candidates using the manifest/module docs and pick the next non-Go pilot. It must not start Go/Fiber/Go Worker admission.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/oa-pending-payments/state-machine.md`

No state definition changes are needed. This slice removes a legacy app-level rebuild path and updates execution accounting, but it does not add a new read model state or module state transition.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no OA payment status, matching, amount, promotion, writeback or relation business rule changed.
2. Service-layer tests: applicable through the updated API/service boundary guard proving legacy app-level rebuild helpers are removed.
3. API contract tests: applicable as regression coverage; targeted OA pending payment API tests still cover rows/detail freshness and response shapes.
4. Read model/cache/background job tests: applicable; targeted invoice usage collection runtime tests cover OA projection builder fan-out/rebuild/save/mark/prune and stale source-version handling.
5. Frontend component and interaction tests: not changed in this slice; previous frontend barrier tests remain the relevant coverage.
6. End-to-end business-flow integration tests: not run; the deleted app helpers had no runtime caller and no UI/API behavior changed.
7. Existing feature regression tests: applicable; regression tests guard against old `Application` rebuild helpers returning and preserve OA read model API/projection behavior.

## Verification

Required for this slice:

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py tests/test_oa_pending_payment_api.py
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api.OaPendingPaymentReadModelRepositoryPortTests tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_legacy_application_rebuild_helpers_are_removed tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_rows_repository_unavailable_enqueues_refresh_without_live_scan tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_rows_source_version_stale_enqueues_refresh_without_stale_rows tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_rows_relation_source_version_stale_enqueues_refresh_without_stale_rows tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_all_scope_fresh_rows_do_not_require_all_scope_row_or_enqueue_refresh tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_expected_source_versions_use_workbench_relation_repository_not_oa_repository tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_detail_routes_use_sql_read_model_without_live_scan tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_detail_stale_or_missing_read_model_refreshes_without_live_scan -v
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_persists_invoice_relation_source_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_persists_grouped_oa_pending_payment_relation_as_one_row tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_reads_completed_from_unified_projection_and_in_progress_from_admission tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_marks_empty_scopes_with_source_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_prunes_invoice_usage_collection_scope_shards tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_refresh_handler_expands_all_scopes_and_completes_with_source_version tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_oa_refresh_handler_skips_stale_source_version_before_rebuild -v
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only local OA pending payment implementation support is accounted for. The `oa_pending_payment` module is not globally closed because production PostgreSQL/worker/App Status/high-row/browser evidence remains deferred.
