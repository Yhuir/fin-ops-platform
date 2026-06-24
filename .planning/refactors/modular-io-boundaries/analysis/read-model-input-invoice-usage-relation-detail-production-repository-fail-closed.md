# Read Model Input Invoice Usage Relation Detail Production Repository Fail-Closed

**Date:** 2026-06-24
**Boundary:** `read-models:input-invoice-usage-relation-detail-production-repository-fail-closed`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

During `read-models:input-invoice-usage-local-implementation-closure-audit`, verify whether relation detail reads are fully protected by the SQL read model fresh gate in production PostgreSQL runtime. The audit found a concrete gap, so the closure audit was split and this narrower implementation slice was executed first.

## Gap

`/api/input-invoice-usage/rows/{row_id}/relation-details` already used `InputInvoiceUsageReadModelDetailService` when `get_input_invoice_usage_row_by_row_id(...)` was available. However, when the repository was missing, `_get_input_invoice_usage_relation_details_from_sql_read_model(...)` returned `None`, and `_handle_api_input_invoice_usage_relation_details(...)` fell back to `InputInvoiceUsageQueryService.row_relation_details(...)`.

That fallback is acceptable only for local/legacy runtime. In production PostgreSQL runtime, missing SQL read repository must return `202`/`read_model_status=refreshing` and enqueue refresh instead of live rebuilding detail payload.

## Implementation

Changed:

- `InputInvoiceUsageReadModelDetailService._refreshing_payload(...)` became public `refreshing_payload(...)` so the route can reuse the same unavailable-detail contract when no repository exists.
- `Application._get_input_invoice_usage_relation_details_from_sql_read_model(...)` now checks `_requires_sql_read_model_runtime()` when the repository lacks `get_input_invoice_usage_row_by_row_id(...)`.
- In production SQL runtime, missing repository now:
  - enqueues `input_invoice_usage:all` with reason `api_detail_sql_repository_unavailable`;
  - returns the standard relation-detail refreshing payload;
  - prevents live query fallback.

Added:

- `InputInvoiceUsageApiTests.test_relation_details_require_sql_repository_in_production_without_live_rebuild`

## Preserved Behavior

- Fresh SQL read model row detail still returns `read_model_status=fresh`.
- Stale/source-version-mismatch detail behavior remains unchanged.
- Local/legacy runtime can still fall back to the query service when no SQL repository is configured.
- API response shape for refreshing detail uses the existing `detailAvailable=false`, `read_model_status=refreshing`, `readModelStatus=refreshing`, `read_model_scope_key=all` contract.
- OA reverse draft creation, target applicant credentials/token flow, Workbench relation commands, payment status rules, worker event types, read model schema and frontend behavior are unchanged.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/input-invoice-usage/state-machine.md`

No state definition changes are required. This slice enforces an existing read model state rule: production relation detail reads must not fall back to live scan when SQL read model runtime is required.

Transition:

- Original selected queue item: `read-models:input-invoice-usage-local-implementation-closure-audit`
- Split implementation boundary: `read-models:input-invoice-usage-relation-detail-production-repository-fail-closed`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:input-invoice-usage-local-implementation-closure-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Category Decision

1. Business core unit tests: not directly applicable; payment/OA/relation business rules are unchanged.
2. Service-layer tests: applicable; `InputInvoiceUsageReadModelDetailService.refreshing_payload(...)` preserves the service-owned detail-unavailable contract.
3. API contract tests: applicable; added API regression proving production missing repository returns `202 refreshing` and does not live rebuild relation details.
4. Read model/cache/background job tests: applicable; verified the refreshing path enqueues `input_invoice_usage:all` through the gateway-backed queue wrapper. Existing runtime tests continue to cover rows miss/unavailable behavior.
5. Frontend component and interaction tests: not directly applicable; frontend already handles detail `read_model_status=refreshing`, and no UI behavior changed.
6. End-to-end business-flow integration tests: not directly applicable for this narrow fail-closed guard; OA reverse and payment-rule flows are unchanged.
7. Existing feature regression tests: applicable; reran fresh detail and scoped source-version detail regressions.

## Verification

```bash
python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/services/input_invoice_usage_read_model_detail_service.py tests/test_input_invoice_usage_api.py
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_relation_details_require_sql_repository_in_production_without_live_rebuild tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_relation_details_use_input_invoice_usage_read_model_row_without_live_rebuild tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_relation_details_compare_source_versions_with_row_scope -v
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_requires_sql_repository_in_production_without_live_scan tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_input_api_miss_enqueues_refresh_without_live_scan -v
```

## Completion Claim

Only the relation-detail production repository fail-closed slice is closed. `input_invoice_usage` remains implementation-gap-open; the local closure/defer audit must run next and decide whether additional migration is needed before production-evidence defer.
