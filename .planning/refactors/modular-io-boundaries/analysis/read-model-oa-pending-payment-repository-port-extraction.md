# Read Model OA Pending Payment Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:oa-pending-payment-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Add a narrow OA pending payment read-model repository port and wire OA rows/detail/projection save/mark/prune paths through it without changing OA payment status semantics, OA MySQL write-back, payment-admitted source adapter behavior, pending relation promotion, command service behavior, UI workflow, shared worker event semantics, production state or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-pending-invoice.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
- `docs/modules/read-models/README.md`
- `docs/modules/oa-pending-payments/README.md`
- `docs/modules/oa-pending-payments/tests.md`
- `docs/modules/oa-pending-payments/implementation-notes.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/oa_pending_payment_read_model_service.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_read_model_refresh.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `tests/test_oa_pending_payment_api.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`

CodeGraph was used to locate `OaPendingPaymentReadModelService` and `InvoiceUsageCollectionSqlProjectionBuilder` before editing.

## Implementation

Added `OaPendingPaymentReadModelRepositoryPort` with the OA pending payment read-model methods currently registered in `READ_MODEL_MANIFEST`:

- `list_oa_pending_payment_rows`
- `save_oa_pending_payment_rows`
- `mark_oa_pending_payment_scope`
- `prune_oa_pending_payment_scope_shards`
- `get_oa_pending_payment_row_by_row_id`
- `get_oa_pending_payment_row_by_oa_id`
- `get_oa_pending_payment_row_by_bank_transaction_id`
- `get_oa_pending_payment_row_by_invoice_id`

Wiring changes:

- `PostgresStateStore.oa_pending_payment_sql_read_repository` now returns `OaPendingPaymentReadModelRepositoryPort`.
- `InvoiceUsageCollectionSqlProjectionBuilder` accepts `oa_pending_payment_read_model_repository` and uses it for OA pending payment save/mark/prune paths.
- `app/worker.py` wraps the worker `PostgresReadModelRepository` in `OaPendingPaymentReadModelRepositoryPort` for the OA pending payment projection path.
- `Application._oa_pending_payment_expected_source_versions(...)` now reads Workbench relation source versions from `_workbench_relation_sql_read_repository`, not from the OA pending payment repository.

## Scope Decision

Workbench relation source versions are deliberately not part of `OaPendingPaymentReadModelRepositoryPort`.

Reason:

- `workbench_relation_source_versions(...)` is owned by the `workbench_relation` read-model boundary;
- exposing it through the OA pending payment port would mix relation facts into the OA repository surface;
- the existing `WorkbenchRelationReadModelRepositoryPort` already owns that method.

The app-level source-version provider now composes OA source versions with Workbench relation source versions from the Workbench relation port.

## Legacy Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| Broad `PostgresReadModelRepository` in OA pending payment read route | replaced in PostgreSQL state store | `oa_pending_payment_sql_read_repository` now returns the narrow port. |
| Broad repository in `OaPendingPaymentReadModelService` unit tests | test fixture compatibility | Existing tests still inject fakes directly and exercise the public service/API contract. |
| Broad repository in `InvoiceUsageCollectionSqlProjectionBuilder` | retained for input/output invoice usage only | OA pending payment save/mark/prune now uses the OA port; input/output usage remains unchanged in this slice. |
| Workbench relation source-version lookup through OA repository | removed | Source-version provider now reads relation versions from the Workbench relation repository port. |
| OA MySQL write-back / pending relation promotion / command service | untouched | These are command-side boundaries and are outside repository port extraction. |

## State Machine Impact

No state definition changed.

The state transition is slice-only:

- `read-models:oa-pending-payment-repository-port-extraction`: `pending` -> `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:oa-pending-payment-refresh-freshness-operation-barrier-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no OA payment status/write-back/business rules changed.
2. Service-layer tests: applicable; new port guard proves unrelated repository methods are not exposed and source-version owner is Workbench relation.
3. API contract tests: applicable through targeted OA pending payment API tests preserving refreshing/source-version behavior.
4. Read model/cache/background job tests: applicable through invoice usage collection SQL runtime tests for OA save/mark/prune and fan-out behavior.
5. Frontend component and interaction tests: not applicable; no frontend behavior or response shape changed.
6. End-to-end business-flow integration tests: not applicable for this narrow repository port extraction.
7. Existing feature regression tests: applicable; targeted OA API and projection regression tests were rerun.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/oa_pending_payment_read_model_repository.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py backend/src/fin_ops_platform/app/worker.py backend/src/fin_ops_platform/app/server.py tests/test_oa_pending_payment_api.py tests/test_invoice_usage_collection_sql_runtime.py
PYTHONPATH=backend/src python3 -m unittest tests.test_oa_pending_payment_api.OaPendingPaymentReadModelRepositoryPortTests tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_rows_repository_unavailable_enqueues_refresh_without_live_scan tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_rows_source_version_stale_enqueues_refresh_without_stale_rows tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_production_rows_relation_source_version_stale_enqueues_refresh_without_stale_rows tests.test_oa_pending_payment_api.OaPendingPaymentApiTests.test_expected_source_versions_use_workbench_relation_repository_not_oa_repository -v
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_persists_invoice_relation_source_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_persists_grouped_oa_pending_payment_relation_as_one_row tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_reads_completed_from_unified_projection_and_in_progress_from_admission tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_marks_empty_scopes_with_source_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_prunes_invoice_usage_collection_scope_shards tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_refresh_handler_expands_all_scopes_and_completes_with_source_version -v
```

Final slice verification must additionally run:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only the OA pending payment repository port extraction slice is closed. `oa_pending_payment` remains `implementation-gap-open`, and Go hot-path admission remains blocked.
