# Read Model Input Invoice Usage Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:input-invoice-usage-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Extract a narrow repository port for the `input_invoice_usage` read model so rows/detail reads and projection save/mark/prune paths no longer depend on the broad `PostgresReadModelRepository` surface.

This is a narrow implementation slice. It does not change input invoice usage business behavior, API response shape, read model schema, worker event type, operation barrier behavior, OA reverse workflow, payment status rules, Go/Fiber/Go Worker admission, or production state.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-oa-pending-payment.md`
- `docs/modules/read-models/README.md`
- `docs/modules/read-models/tests.md`
- `docs/modules/read-models/implementation-notes.md`
- `docs/modules/input-invoice-usage/README.md`
- `docs/modules/input-invoice-usage/state-machine.md`
- `docs/modules/input-invoice-usage/tests.md`
- `docs/modules/input-invoice-usage/implementation-notes.md`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `tests/test_input_invoice_usage_api.py`
- `tests/test_invoice_usage_collection_sql_runtime.py`

CodeGraph was used before editing to inspect existing port patterns (`OaPendingPaymentReadModelRepositoryPort`, `PendingInvoiceReadModelRepositoryPort`), the `PostgresStateStore.input_invoice_usage_sql_read_repository` property, and `InvoiceUsageCollectionSqlProjectionBuilder.rebuild_input_invoice_usage_read_model_scope(...)`.

## Implementation

Added:

- `backend/src/fin_ops_platform/services/input_invoice_usage_read_model_repository.py`

Changed:

- `PostgresStateStore.input_invoice_usage_sql_read_repository` now returns `InputInvoiceUsageReadModelRepositoryPort` instead of the broad `PostgresReadModelRepository`.
- `InvoiceUsageCollectionSqlProjectionBuilder` accepts `input_invoice_usage_read_model_repository` and uses it for:
  - `save_input_invoice_usage_rows`
  - `mark_input_invoice_usage_scope`
  - `prune_input_invoice_usage_scope_shards`
- `RuntimeWorker` invoice-usage collection builder wiring injects `InputInvoiceUsageReadModelRepositoryPort(read_model_repository)`.
- `tests/test_invoice_usage_collection_sql_runtime.py` adds `InputInvoiceUsageReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`.

## Boundary Decision

`list_input_invoice_usage_scope_shards(...)` is intentionally not part of `InputInvoiceUsageReadModelRepositoryPort`.

Reason:

- it is source-fact month enumeration for fan-out;
- it is not in `READ_MODEL_MANIFEST["input_invoice_usage"].repository_port_contract`;
- keeping it outside the repository port prevents read-model persistence ownership from absorbing source-fact discovery.

The existing `InvoiceUsageCollectionSqlProjectionBuilder.list_input_invoice_usage_scope_shards(...)` remains the worker fan-out boundary for this slice.

## Preserved Behavior

- Rows/filter-options/export/detail response shape is unchanged.
- `read_model_status`, stale reasons, refresh enqueue behavior and source-version proof are unchanged.
- `input_invoice_usage:all` remains fan-out control scope with all-query freshness proven by month rows/scopes and dirty/outbox state.
- OA reverse draft creation, target applicant credentials/token handling, Workbench relation command behavior and payment status rules are unchanged.
- `output_invoice_collection` and `oa_pending_payment` still share the worker family but use their own repository surfaces.

## Legacy / Contamination Accounting

| Surface | Classification | Status |
| --- | --- | --- |
| Broad `PostgresReadModelRepository` behind state-store input usage property | removed from public input usage state-store surface | Replaced by `InputInvoiceUsageReadModelRepositoryPort`. |
| Broad `PostgresReadModelRepository` inside `InvoiceUsageCollectionSqlProjectionBuilder` | retained for output collection and non-input shared dependencies | Input usage save/mark/prune no longer use it. |
| `Application` input usage SQL helper methods | retained for later audit | They now receive the state-store port in PostgreSQL runtime, but app-level rebuild/list/mark helper ownership still needs a dedicated freshness/legacy audit. |
| `list_input_invoice_usage_scope_shards(...)` | source-fact fan-out boundary | Explicitly kept outside repository port. |

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/input-invoice-usage/state-machine.md`

No state definition changes are required. This slice changes repository ownership/wiring, not business states or read model lifecycle states.

Transition:

- Previous queue item: `read-models:input-invoice-usage-repository-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:input-invoice-usage-refresh-freshness-operation-barrier-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Category Decision

1. Business core unit tests: not directly applicable; payment status, OA reverse and relation business rules are unchanged.
2. Service-layer tests: applicable; added repository port guard proving the input usage port excludes unrelated read model methods.
3. API contract tests: applicable as regression; targeted input usage relation-detail/export tests preserve public response behavior.
4. Read model/cache/background job tests: applicable; targeted invoice-usage collection SQL runtime tests cover input rows/detail, repository unavailable, source-version mismatch, all-scope fan-out/prune and projection save/mark/prune behavior.
5. Frontend component and interaction tests: not applicable in this slice; no UI/API shape or operation barrier target behavior changed.
6. End-to-end business-flow integration tests: not directly applicable for repository port extraction; OA reverse and relation flows are unchanged.
7. Existing feature regression tests: applicable; input usage API/projection tests preserve rows/detail/export/freshness behavior.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/input_invoice_usage_read_model_repository.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py backend/src/fin_ops_platform/app/worker.py tests/test_invoice_usage_collection_sql_runtime.py
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime.InputInvoiceUsageReadModelRepositoryPortTests tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_repository_returns_fresh_empty_scope_without_api_miss tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_repository_uses_native_bank_account_and_direction_columns tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_repository_save_persists_bank_account_and_direction_columns tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_repository_prunes_orphan_scope_shards tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_repository_detail_lookup_uses_row_id_native_column tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_miss_enqueues_refresh_without_live_scan tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_requires_sql_repository_in_production_without_live_scan tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_source_version_miss_enqueues_refresh_without_stale_rows tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_relation_source_version_mismatch_enqueues_refresh_without_stale_rows tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_all_scope_uses_rows_when_month_relation_versions_differ tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_all_scope_recovers_after_orphan_scope_prune tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_persists_invoice_relation_source_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_projection_keeps_current_scope_relation_versions_after_cross_month_fallback tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_marks_empty_scopes_with_source_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_prunes_invoice_usage_collection_scope_shards tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_refresh_handler_expands_all_scopes_and_completes_with_source_version -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_relation_details_use_input_invoice_usage_read_model_row_without_live_rebuild tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_export_preview_and_download_use_current_input_invoice_usage_filters -v
```

The first attempted targeted unittest command included four stale test names; that command failed at test discovery only. It was corrected to the real test names above, and all selected tests passed.

## Completion Claim

Only the repository port extraction slice is closed. `input_invoice_usage` remains implementation-gap-open because freshness/force-refresh/operation-barrier behavior, app-level helper legacy classification, production PostgreSQL/worker/App Status/high-row/browser evidence and local closure/defer accounting still need later slices.
