# Fix Input Invoice Usage All-Scope Refresh Loop Summary

## Result

Implemented the read model convergence fix for the `/input-invoice-usage` all-scope refreshing loop.

The bug was a read model cleanup gap, not a frontend polling issue. `input_invoice_usage:all` refresh only fanned out current month shards. Old month rows/scopes that no longer belonged to the current input invoice fact set stayed in `read_model.input_invoice_usage_*`, so all-scope source version aggregation included stale `oa_projection_sync_version` values and produced `oa_projection_sync_version_missing`.

## Changes

- Added SQL read model pruning for invoice relation page read models:
  - `input_invoice_usage`
  - `output_invoice_collection`
  - `oa_pending_payment`
- Wired all-scope fan-out refresh to call the projection builder prune hook after discovering current shards and before completing the parent dirty scope.
- Preserved fail-closed source version checks; API still returns refreshing when actual source versions are missing or stale.
- Added an API-level regression proving the failure mode and recovery:
  - stale orphan scope causes `read_model_status=refreshing` with `oa_projection_sync_version_missing`
  - pruning to the current shard set makes the same all-scope API path return `fresh`
- Updated module docs and read model governance docs.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_repository_prunes_orphan_scope_shards \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_all_scope_recovers_after_orphan_scope_prune \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_prunes_invoice_usage_collection_scope_shards \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_refresh_handler_expands_all_scopes_and_completes_with_source_version \
  -v

PYTHONPATH=backend/src python3 -m unittest \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_all_scope_recovers_after_orphan_scope_prune \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_all_scope_uses_rows_when_month_relation_versions_differ \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_source_version_miss_enqueues_refresh_without_stale_rows \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_relation_source_version_mismatch_enqueues_refresh_without_stale_rows \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_repository_prunes_orphan_scope_shards \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_prunes_invoice_usage_collection_scope_shards \
  tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_refresh_handler_expands_all_scopes_and_completes_with_source_version \
  -v

PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_freshness -v
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api -v
bash scripts/verify.sh docs
```

Broader suite note:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime tests.test_read_model_freshness -v
```

This broader command still has 4 existing `output_invoice_collection` errors because the test-created `Application` lacks `_workbench_query_service` after unrelated output collection changes. The input usage and freshness tests in that command passed.

## Remaining Risk

The local PostgreSQL read model tables were not mutated during this quick. Existing environments that already contain orphan month shards still need the updated worker to run `input_invoice_usage:all` refresh, or an operator can perform an equivalent read model refresh/repair using the production durable queue path.
