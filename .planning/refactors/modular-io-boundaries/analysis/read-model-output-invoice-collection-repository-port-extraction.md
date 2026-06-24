# Output Invoice Collection Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:output-invoice-collection-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Previous State

- `output_invoice_collection` was selected as the sixth non-Go read model implementation pilot.
- The manifest already required a disjoint repository port contract:
  - `list_output_invoice_collection_rows`
  - `save_output_invoice_collection_rows`
  - `mark_output_invoice_collection_scope`
  - `prune_output_invoice_collection_scope_shards`
- PostgreSQL runtime reads obtained `output_invoice_collection_sql_read_repository` from `PostgresStateStore`, but that property still returned the broad `PostgresReadModelRepository`.
- `InvoiceUsageCollectionSqlProjectionBuilder` routed output save/mark/prune calls directly through its broad `_read_repository`, while input usage and OA pending payment already used narrow ports.

## Selected Boundary

Add a narrow `OutputInvoiceCollectionReadModelRepositoryPort`, return it from PostgreSQL state-store output read wiring, and route output projection save/mark/prune operations through it.

This slice deliberately does not change lifecycle writes, receipt facts, red/blue relation commands, frontend behavior, worker runtime, queue schema, Go/Fiber/Go Worker admission, or production state.

## Implementation

Runtime code:

- Added `backend/src/fin_ops_platform/services/output_invoice_collection_read_model_repository.py`.
- `OutputInvoiceCollectionReadModelRepositoryPort` exposes only the manifest-listed output collection methods:
  - `list_output_invoice_collection_rows(...)`
  - `save_output_invoice_collection_rows(...)`
  - `mark_output_invoice_collection_scope(...)`
  - `prune_output_invoice_collection_scope_shards(...)`
- `PostgresStateStore.output_invoice_collection_sql_read_repository` now returns `OutputInvoiceCollectionReadModelRepositoryPort`.
- `InvoiceUsageCollectionSqlProjectionBuilder` accepts optional `output_invoice_collection_read_model_repository` and uses it for:
  - `rebuild_output_invoice_collection_read_model_scope(...)` save;
  - `mark_output_invoice_collection_scope_empty(...)`;
  - `prune_output_invoice_collection_scope_shards(...)`.

Tests:

- Added `OutputInvoiceCollectionReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods`.
- Updated projection builder tests so output save/mark/prune assertions exercise `_output_invoice_collection_read_model_repository`.
- Updated `PostgresStateStoreTests.test_read_model_repositories_use_optional_read_connection` to prove the output port wraps the optional SQL read connection.

## Preserved Behavior

Verified unchanged:

- rows/filter/export/detail response shape remains owned by existing API/service paths;
- production missing repository still returns `202`/refreshing and enqueues `output_invoice_collection`;
- stale/schema/source-version mismatch still returns refreshing without stale rows;
- all-scope freshness still uses concrete month/scoped evidence and avoids relation-all loops;
- fresh SQL rows still receive lifecycle overlay before response;
- projection builder still persists output source versions, marks empty scopes and prunes orphan shards.

## Legacy Path Classification

- Broad `PostgresReadModelRepository` remains the SQL/table owner.
- New direct consumers of output read-model query/projection behavior use `OutputInvoiceCollectionReadModelRepositoryPort`.
- Existing app-level output projection helpers in `Application` were not removed in this slice because the current boundary was repository-port extraction only. They remain for the next freshness/helper audit to classify as removed, gateway-backed compat, or blocked.
- No old path was allowed to write canonical facts, dirty scopes, outbox events, readiness, cache, App Status or new authoritative outputs in this slice.

## State Machine Impact

Reviewed:

- `.planning/refactors/modular-io-boundaries/03-REFACTOR-STATE-MACHINE.md`
- `docs/modules/output-invoice-collections/state-machine.md`

No global or module state definition changed. This slice changes implementation accounting only.

Transition:

- Previous queue item: `read-models:output-invoice-collection-repository-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:output-invoice-collection-refresh-freshness-operation-barrier-audit`
- Go hot-path admissions remain `blocked-by-prerequisite`

## Seven Test Categories

| Category | Decision |
| --- | --- |
| 1. Business core unit tests | Not directly applicable. No lifecycle, receipt, red/blue relation, status or amount business rule changed. Existing output service/API tests were rerun for regression. |
| 2. Service-layer tests | Covered. Added port isolation coverage and projection builder save/mark/prune routing coverage. |
| 3. API contract tests | Covered by rerunning output API tests and targeted SQL runtime API tests; API shape and refreshing/fresh statuses are unchanged. |
| 4. Read model/cache/background job tests | Covered by `tests.test_invoice_usage_collection_sql_runtime`, including source versions, stale/source mismatch, all fan-out proof and projection save/mark/prune. No cache or worker runtime code changed. |
| 5. Frontend component and interaction tests | Not applicable for this slice because no frontend API shape, barrier target or UI behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this repository-port extraction because lifecycle/receipt/red-blue flows were not changed; existing API/runtime integration regression was rerun. |
| 7. Existing feature regression tests | Covered by output API and invoice usage collection SQL runtime regression commands. |

## Verification

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/output_invoice_collection_read_model_repository.py backend/src/fin_ops_platform/services/invoice_usage_collection_sql_projection.py backend/src/fin_ops_platform/services/postgres_state_store.py tests/test_invoice_usage_collection_sql_runtime.py tests/test_postgres_state_store.py
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime.OutputInvoiceCollectionReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_persists_invoice_relation_source_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_marks_empty_scopes_with_source_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_projection_builder_prunes_invoice_usage_collection_scope_shards tests.test_postgres_state_store.PostgresStateStoreTests.test_read_model_repositories_use_optional_read_connection -v
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_output_api_requires_sql_repository_in_production_without_live_scan tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_output_api_schema_stale_enqueues_refresh_when_unified_relation_fields_missing tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_output_api_all_scope_does_not_loop_on_relation_all_versions tests.test_invoice_usage_collection_sql_runtime.InvoiceUsageCollectionSqlRuntimeTests.test_output_api_stale_returns_refreshing_without_stale_rows tests.test_output_invoice_collection_api.OutputInvoiceCollectionApiTests.test_sql_fresh_rows_route_applies_lifecycle_overlay_before_response -v
PYTHONPATH=backend/src python3 -m unittest tests.test_invoice_usage_collection_sql_runtime -v
PYTHONPATH=backend/src python3 -m unittest tests.test_output_invoice_collection_api -v
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
```

## Completion Claim

This slice closes only the repository port extraction boundary. It does not close `output_invoice_collection`, the read model roadmap, or any Go hot-path gate.
