# Deferred Items

## 40-03 verification discoveries

- `tests/test_postgres_state_store_integration.py::PostgresStateStoreIntegrationTests::test_bank_flow_rule_batch_page_uses_sql_pagination_and_aggregate_summary` expects the removed `PostgresStateStore.save_bank_flow_rule_batches` API.
- `tests/test_postgres_state_store_integration.py::PostgresStateStoreIntegrationTests::test_bank_flow_rule_batch_canonical_query_reads_without_projection_rows` expects a legacy `total` response field absent from the current canonical query result.
- `tests/test_postgres_state_store_integration.py::PostgresStateStoreIntegrationTests::test_save_no_oa_bank_batches_replaces_absent_read_model_rows` expects the retired no-OA read-model writer to repopulate `read_model.no_oa_bank_batch_rows`.

These failures pre-existed the 40-03 production change and are outside its import batch-row hotspot scope. They require separate test retirement or contract reconciliation; 40-03 does not alter Bank/Turnover/read-model behavior.
