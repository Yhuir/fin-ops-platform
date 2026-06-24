# Read Model Output Invoice Collection Relation Detail Production Repository Fail-Closed

**Date:** 2026-06-24
**Boundary:** `read-models:output-invoice-collection-relation-detail-production-repository-fail-closed`
**Previous planned boundary:** `read-models:output-invoice-collection-local-implementation-closure-audit`
**Result state:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

- `output_invoice_collection` repository port extraction was implemented.
- Rows, filter options and export already used SQL read model fresh gates in production PostgreSQL runtime.
- Lifecycle, receipt and red/blue relation mutation responses exposed `read_model_scope_keys` / `freshness_targets`; frontend write-after-read flows wait on concrete month operation barrier targets when available.
- Unused app-level output projection helpers were removed from `Application`.
- The planned local closure audit still had to classify `/api/output-invoice-collections/rows/{row_id}/relation-details`.

## Finding

The local closure audit found a concrete implementation gap before closure accounting could proceed:

- `OutputInvoiceCollectionApiRoutes.relation_details(...)` always called `OutputInvoiceCollectionQueryService.row_relation_details(...)`.
- In production PostgreSQL runtime, if the SQL read repository was missing or lacked a row detail lookup, the route could live rebuild relation details instead of returning `read_model_status=refreshing`.
- Unlike `input_invoice_usage`, `output_invoice_collection` had no read-model detail service and no repository-port row lookup for relation details.

This means the slice could not be marked `production-evidence-deferred` yet. The correct transition was to split and implement this narrower boundary first.

## Implementation

Runtime changes:

- Added `OutputInvoiceCollectionReadModelDetailService`.
- Added `output_invoice_collection_relation_details_from_row(...)` and reused it from both live query and SQL read-model detail paths.
- Added `get_output_invoice_collection_row_by_row_id(...)` to:
  - `OutputInvoiceCollectionReadModelRepositoryPort`;
  - `PostgresReadModelRepository`;
  - `READ_MODEL_MANIFEST["output_invoice_collection"].repository_port_contract`.
- Wired `OutputInvoiceCollectionApiRoutes` with `sql_relation_details_provider`.
- Added `Application._get_output_invoice_collection_relation_details_from_sql_read_model(...)`.
- `Application._handle_api_output_invoice_collections_relation_details(...)` now returns `202` when the provider returns a refreshing payload.

Production behavior:

- When `_requires_sql_read_model_runtime()` is true and the output SQL read repository does not expose `get_output_invoice_collection_row_by_row_id(...)`, relation details return:
  - HTTP `202`;
  - `read_model_status=refreshing`;
  - `read_model_scope_key=all`;
  - `detailAvailable=false`;
  - refresh enqueue `output_invoice_collection:all` with reason `api_detail_sql_repository_unavailable`.
- Fresh SQL read-model detail rows return `200` and build the same relation-detail payload shape without calling the live query service.

## Preserved Behavior

- Existing live/local mode remains available when production SQL runtime is not required.
- Existing relation detail response shape is preserved for fresh rows.
- Receipt, red/blue relation, lifecycle state transitions, UI behavior, worker runtime, queue schema and Go/Fiber/Go Worker admission are unchanged.
- `output_invoice_collection:all` remains a fan-out control scope; this slice only uses it as the conservative detail miss/unavailable enqueue target when no row/month lookup is possible.

## Legacy Path Classification

- `OutputInvoiceCollectionQueryService.row_relation_details(...)` remains a legacy/local compatible read path for non-production SQL runtime and local in-memory tests.
- In production PostgreSQL runtime, relation details must use `OutputInvoiceCollectionReadModelDetailService` when the SQL detail lookup exists, or return refreshing/enqueue when it does not.
- The live detail path must not write canonical facts, dirty scopes, outbox events, read model readiness, cache, App Status or new authoritative outputs.

## State-Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/output-invoice-collections/state-machine.md`

No global or module state definition changed. This slice changes implementation accounting only:

- `read-models:output-invoice-collection-local-implementation-closure-audit` was split because it found a concrete local gap.
- `read-models:output-invoice-collection-relation-detail-production-repository-fail-closed` is `implementation-closed`.
- `read-models:output-invoice-collection-local-implementation-closure-audit` remains the next pending boundary.
- Go hot-path admissions remain `blocked-by-prerequisite`.

## Seven Test Categories

1. Business core unit tests: not directly applicable. No receipt, collection status, red/blue relation, status rule, amount or lifecycle business rule changed.
2. Service-layer tests: applicable. Added read-model detail service behavior through API tests and repository port coverage.
3. API contract tests: applicable. Added output collection relation detail production fail-closed and fresh SQL detail response tests.
4. Read model/cache/background job tests: applicable. Updated manifest and repository-port coverage so output detail lookup is registered and isolated on the output read-model port.
5. Frontend component and interaction tests: not applicable. API shape remains compatible; frontend behavior and component code did not change.
6. End-to-end business-flow integration tests: not applicable for this narrow backend fail-closed slice. Existing Browser flows continue to cover relation detail UI, lifecycle, receipt and export paths.
7. Existing feature regression tests: applicable. Existing output relation detail test still passes, proving the local/live relation detail behavior is preserved outside production SQL fail-closed mode.

## Verification

Target verification executed during the slice:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_output_invoice_collections.py backend/src/fin_ops_platform/services/output_invoice_collection_service.py backend/src/fin_ops_platform/services/output_invoice_collection_read_model_detail_service.py backend/src/fin_ops_platform/services/output_invoice_collection_read_model_repository.py backend/src/fin_ops_platform/services/postgres_repositories/read_models.py tests/test_output_invoice_collection_api.py tests/test_invoice_usage_collection_sql_runtime.py tests/test_read_model_manifest.py
PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_relation_details_require_sql_repository_in_production_without_live_rebuild tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_relation_details_use_fresh_sql_read_model_row_without_live_rebuild tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_invoice_relation_details_returns_all_related_output_invoices tests.test_invoice_usage_collection_sql_runtime.OutputInvoiceCollectionReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods tests.test_read_model_manifest.ReadModelManifestTests.test_invoice_lifecycle_and_usage_manifest_preserve_scoped_contracts -v
```

Additional verification executed before commit:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api tests.test_invoice_usage_collection_sql_runtime tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_service tests.test_output_invoice_collection_lifecycle -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risks

- No local `PGSQL_URL` or staging database, so real PostgreSQL dirty/outbox/readiness and worker drain are not proved.
- No production write was performed; production evidence remains deferred.
- Output collection local implementation closure still requires a separate accounting slice after this fix.
- Go/Fiber/Go Worker admission remains blocked.

## Next Boundary

`read-models:output-invoice-collection-local-implementation-closure-audit`
