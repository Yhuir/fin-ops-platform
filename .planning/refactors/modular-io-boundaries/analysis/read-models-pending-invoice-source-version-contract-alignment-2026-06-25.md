# Pending Invoice Source Version Contract Alignment - 2026-06-25

**Boundary:** `read-models:pending-invoice-source-version-contract-alignment`
**Status:** `implementation-closed`
**Module closure:** `not-module-closed`
**Production mutation:** forbidden
**Previous boundary:** `production:pending-invoice-no-oa-source-version-contract-deep-diagnosis`
**Next boundary:** `production:pending-invoice-source-version-contract-deploy-and-convergence-runbook`

## Goal

Fix the local code-contract gaps found by Row275 before any production rebuild/convergence operation:

- align pending invoice API expected source versions with the SQL projection writer contract;
- prevent aggregate `direction:filter` source-version proof from being poisoned by zero-row historical month shards.

## Inputs Reviewed

- `analysis/production-pending-invoice-no-oa-source-version-contract-deep-diagnosis-2026-06-25.md`
- `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `backend/src/fin_ops_platform/services/postgres_repositories/read_models.py`
- `tests/test_search_pending_sql_runtime.py`
- `tests/test_pending_invoice_api.py`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/tests.md`
- `docs/modules/pending-invoices/implementation-notes.md`

CodeGraph was used to confirm the relevant symbols and call path:

- `pending_invoice_source_versions(...)`
- `PendingInvoiceSourceVersionsProvider.__call__(...)`
- `SearchPendingSqlProjectionBuilder._pending_invoice_source_versions(...)`
- `PostgresReadModelRepository._pending_invoice_scope_row(...)`
- `_pending_invoice_scope_source_versions_row(...)`
- `test_pending_invoice_repository_aggregates_bank_detail_source_versions_across_month_shards(...)`

## Changes

- `pending_invoice_source_versions(...)` now includes `invoice_lifecycle_policy_schema_version` from `INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION`, matching the SQL projection writer.
- `pending_invoice_source_versions(...)` now always emits stable `bank_detail_source_versions` and `workbench_relation_source_versions` dict keys, matching the SQL projection writer's stable output shape.
- `PostgresReadModelRepository._pending_invoice_scope_row(...)` now selects `row_count` from `read_model.pending_invoice_scopes`.
- `_pending_invoice_scope_source_versions_row(...)` now uses non-empty shard rows (`row_count > 0`) as the effective aggregate source-version set when any exist, falling back to all rows only when every shard is empty or row counts are unavailable.
- Tests now cover writer/API source-version parity and zero-row historical shard aggregate behavior.
- Pending invoice module docs now record the source-version contract and regression coverage.

## Architecture Notes

- `server.py` was not touched.
- No service received `Application` or HTTP dependencies.
- SQL table details remain inside `PostgresReadModelRepository`.
- Read model refresh/enqueue behavior was not changed.
- Month-shard rebuild semantics remain unchanged.
- No production command, deploy, rebuild, requeue, repair or readiness mutation occurred in this boundary.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_pending_invoice_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards -v
python3 -m py_compile backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_search_pending_sql_runtime.py
```

Still required before production closure:

- Deploy this code to production through a bounded controlled runbook.
- Rebuild or refresh explicit pending invoice scopes required for `expense:all`.
- Prove `/health/ready`, dirty scopes, outbox, App Status/read-model freshness and sanitized authenticated API metadata converge.

## Seven Test Categories

- Business core unit tests: not applicable; no business state transition or amount/rule classification changed.
- Service-layer tests: covered by `tests.test_search_pending_sql_runtime` for read model service/provider behavior and freshness outcomes.
- API contract tests: covered by `tests.test_pending_invoice_api`; response shape remains compatible while freshness gate source-version contract changed.
- Read model, cache, and background job tests: covered by `tests.test_search_pending_sql_runtime` for projection writer/source-version parity, aggregate scope source-version proof and stale enqueue behavior.
- Frontend component and interaction tests: not applicable; no frontend/API response shape/UI behavior changed.
- End-to-end business-flow integration tests: not applicable in this local code boundary; production convergence is intentionally deferred to the next controlled runbook.
- Existing feature regression tests: covered by the full `tests.test_search_pending_sql_runtime` file and `tests.test_pending_invoice_api`.

## Remaining Risk

Local tests prove the contract fix, but production rows remain on the currently deployed release until a deploy and explicit-scope convergence runbook completes. no-OA `bank_transaction_category_snapshot_version_mismatch` remains a separate open production freshness issue after pending invoice convergence.
