# Read Model Pending Invoice Repository Port Extraction

**Date:** 2026-06-24
**Boundary:** `read-models:pending-invoice-repository-port-extraction`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Add a narrow pending invoice read-model repository port and wire pending invoice read/service/projection consumers through it without changing pending invoice business rules, API response shape, UI behavior, worker runtime, production state or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/read-model-next-pilot-selection-after-workbench-relation.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-repository-port-and-sql-owner-split-plan.md`
- `.planning/refactors/modular-io-boundaries/analysis/read-model-pending-invoice-and-oa-pending-payment-contract.md`
- `docs/modules/read-models/README.md`
- `docs/modules/pending-invoices/README.md`
- `docs/modules/pending-invoices/tests.md`
- `docs/modules/pending-invoices/implementation-notes.md`
- `backend/src/fin_ops_platform/services/pending_invoice_read_model_service.py`
- `backend/src/fin_ops_platform/services/search_pending_sql_projection.py`
- `backend/src/fin_ops_platform/services/read_model_manifest.py`
- `backend/src/fin_ops_platform/services/postgres_state_store.py`
- `backend/src/fin_ops_platform/app/worker.py`
- `tests/test_search_pending_sql_runtime.py`

## Implementation

Added `PendingInvoiceReadModelRepositoryPort` with the pending invoice read-model methods currently registered in `READ_MODEL_MANIFEST`:

- `list_pending_invoice_rows`
- `list_pending_invoice_filter_options`
- `pending_invoice_source_summary`
- `pending_invoice_bank_detail_source_versions`
- `pending_invoice_workbench_relation_source_versions`
- `save_pending_invoice_rows`
- `mark_pending_invoice_scope`

Wiring changes:

- `PostgresStateStore.pending_invoice_sql_read_repository` now returns `PendingInvoiceReadModelRepositoryPort`.
- `Application._pending_invoice_routes(...)` continues to receive `self._pending_invoice_sql_read_repository`, which is now the narrow port in PostgreSQL runtime and still test-overridable in unit tests.
- `SearchPendingSqlProjectionBuilder` now accepts `pending_invoice_read_model_repository` separately from `read_model_repository`.
- `SearchPendingSqlProjectionBuilder` keeps broad `read_model_repository` for search index behavior and uses the pending invoice port only for pending invoice `save_pending_invoice_rows` / `mark_pending_invoice_scope`.
- `app/worker.py` wraps the worker `PostgresReadModelRepository` in `PendingInvoiceReadModelRepositoryPort` for the pending invoice projection path.

## Scope Decision

`list_pending_invoice_scope_shards` is intentionally not part of `PendingInvoiceReadModelRepositoryPort` in this slice.

Reason:

- current `SearchPendingSqlProjectionBuilder.list_pending_invoice_scope_shards(...)` enumerates source fact months from `app.bank_transactions` through the projection builder connection;
- it is not a `PostgresReadModelRepository` method;
- including it in the read-model repository port would falsely classify source fact enumeration as read-model repository behavior.

If future work extracts pending invoice projection source fact reads, that should be a separate source-fact/provider port.

## Legacy Classification

| Surface | Classification | Reason |
| --- | --- | --- |
| Broad `PostgresReadModelRepository` in pending invoice read route | replaced in PostgreSQL state store | `pending_invoice_sql_read_repository` now returns the narrow port. |
| Broad repository in `PendingInvoiceReadModelService` unit tests | test fixture compatibility | Existing tests directly inject fake repositories; they still exercise the public service contract. |
| Broad repository in `SearchPendingSqlProjectionBuilder` | retained for search index only | The builder owns both search and pending invoice projection; search still needs `save_search_index_rows`. Pending invoice write methods use the new port. |
| `list_pending_invoice_scope_shards` connection SQL | retained source-fact enumeration | Not a read-model repository method; future extraction should be source-fact/provider scoped. |

## State Machine Impact

No state definition changed.

The state transition is slice-only:

- Previous queue item: `read-models:pending-invoice-repository-port-extraction`
- Previous status: `pending`
- New status: `implementation-closed`
- Module closure remains: `implementation-gap-open`
- Next queue item: `read-models:pending-invoice-refresh-freshness-operation-barrier-audit`

## Seven Test Category Decision

1. Business core unit tests: not applicable; no pending invoice status/filter/business rules changed.
2. Service-layer tests: applicable and covered by the new port test plus existing read service/source-version tests.
3. API contract tests: no API contract changed; targeted API-style service tests were rerun to preserve response shape and stale behavior.
4. Read model/cache/background job tests: applicable; existing SQL runtime tests cover rows, source-version stale behavior and search index read path.
5. Frontend component and interaction tests: not applicable; no frontend/UI behavior changed.
6. End-to-end business-flow integration tests: not applicable for this narrow repository port extraction; no cross-page behavior changed.
7. Existing feature regression tests: applicable; targeted pending invoice SQL runtime and search index tests were rerun.

## Verification

Initial verification:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/pending_invoice_read_model_repository.py backend/src/fin_ops_platform/services/postgres_state_store.py backend/src/fin_ops_platform/services/search_pending_sql_projection.py backend/src/fin_ops_platform/app/worker.py tests/test_search_pending_sql_runtime.py
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.PendingInvoiceReadModelRepositoryPortTests.test_port_excludes_unrelated_read_model_methods -v
PYTHONPATH=backend/src python3 -m unittest tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_pending_invoice_repository_reads_rows_page_and_summary tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_pending_invoice_api_workbench_relation_source_version_stale_enqueues_refresh tests.test_search_pending_sql_runtime.SearchPendingSqlRuntimeTests.test_search_api_reads_sql_index -v
```

Final verification must additionally run:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Completion Claim

Only the pending invoice repository port extraction slice is closed. `pending_invoice` remains `implementation-gap-open`, and Go hot-path admission remains blocked.
