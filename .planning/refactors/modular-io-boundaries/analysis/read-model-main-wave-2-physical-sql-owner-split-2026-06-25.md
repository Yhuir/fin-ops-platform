# Read Model Main Closure Wave 2 Physical SQL Owner Split

Date: 2026-06-25

Branch: `main`

Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`

Controller: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`

## Scope Completed In This Wave

This wave completed the physical SQL owner split inside the invoice-family read models:

- `input_invoice_usage`
- `output_invoice_collection`
- `oa_pending_payment`
- `pending_invoice`
- `invoice_lifecycle`

The public narrow ports remain unchanged:

- `InputInvoiceUsageReadModelRepositoryPort`
- `OutputInvoiceCollectionReadModelRepositoryPort`
- `OaPendingPaymentReadModelRepositoryPort`
- `PendingInvoiceReadModelRepositoryPort`
- `InvoiceLifecycleReadModelRepositoryPort`

`PostgresReadModelRepository` now keeps compatibility methods for existing port contracts, but those methods delegate to `PostgresInvoiceUsageCollectionReadModelRepository`. The new owner contains the physical SQL for list/detail/save/mark/prune behavior for the selected family.

`PostgresReadModelRepository` also keeps compatibility methods for `pending_invoice` and `invoice_lifecycle`, but those methods delegate to `PostgresPendingInvoiceLifecycleReadModelRepository`. This owner contains the physical SQL for pending invoice row/filter/source-version reads and writes, plus invoice lifecycle read/write/scope behavior. It receives `bank_detail_scope_summary` as an explicit callable dependency for pending invoice bank-detail source-version checks instead of receiving the full shared repository.

## PSCIP Movement

Before this wave, these three read models were already:

- Partitioned by month-like scope keys through existing scope policy and repository contracts.
- Scoped through read model scope tables and `scope_key` filters.
- Incrementally projected through durable queue events and scoped projection writes.

The gap was ownership: narrow ports wrapped broad shared repository methods whose physical SQL remained inside `PostgresReadModelRepository`.

After the first subwave:

- `input_invoice_usage`, `output_invoice_collection`, and `oa_pending_payment` move from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- No PSCIP-L4 closure is claimed because no production or equivalent runtime evidence was collected.
- No Redis or RabbitMQ freshness source was introduced.
- No broad `all` fake-fresh path was introduced.
- Dirty scope/outbox ownership remains unchanged.

After the second subwave:

- `pending_invoice` and `invoice_lifecycle` also move from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- Pending invoice keeps partitioned/scoped behavior through direction/filter/month scope keys, scoped reads, and source-version aggregation.
- Invoice lifecycle keeps month scope keys, source-version freshness checks, and materialized row reads.
- No PSCIP-L4 closure is claimed because no production or equivalent runtime evidence was collected.

## Guard Added

`tests/test_read_model_manifest.py` now includes `test_invoice_usage_collection_physical_sql_owner_is_split_from_shared_repository`.

The guard proves:

- The selected family methods exist on `PostgresInvoiceUsageCollectionReadModelRepository`.
- `PostgresReadModelRepository` compatibility methods delegate through `_invoice_usage_collection_repository`.
- The shared compatibility methods do not directly reference:
  - `read_model.input_invoice_usage_rows`
  - `read_model.output_invoice_collection_rows`
  - `read_model.oa_pending_payment_rows`

`tests/test_read_model_manifest.py` also includes `test_pending_invoice_lifecycle_physical_sql_owner_is_split_from_shared_repository`.

The guard proves:

- Pending invoice and invoice lifecycle methods exist on `PostgresPendingInvoiceLifecycleReadModelRepository`.
- `PostgresReadModelRepository` compatibility methods delegate through `_pending_invoice_lifecycle_repository`.
- The shared compatibility methods do not directly reference:
  - `read_model.pending_invoice_rows`
  - `read_model.invoice_lifecycle_rows`

`tests/test_read_model_architecture_guards.py` was updated so direct fresh-status classification follows the new invoice lifecycle physical owner class.

## Verification

Commands run:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m pytest tests/test_invoice_usage_collection_sql_runtime.py tests/test_oa_pending_payment_api.py -q
PYTHONPATH=backend/src python3 -m pytest tests/test_search_pending_sql_runtime.py tests/test_invoice_lifecycle_read_model_refresh.py tests/test_invoice_lifecycle_read_facade.py tests/test_invoice_lifecycle_page_integration.py -q
```

Results:

- `tests.test_read_model_manifest`: passed.
- `tests.test_read_model_manifest tests.test_runtime_worker_registry`: passed.
- `tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards`: passed.
- `tests/test_invoice_usage_collection_sql_runtime.py tests/test_oa_pending_payment_api.py`: 67 passed, 5 warnings, 5 subtests passed.
- `tests/test_search_pending_sql_runtime.py tests/test_invoice_lifecycle_read_model_refresh.py tests/test_invoice_lifecycle_read_facade.py tests/test_invoice_lifecycle_page_integration.py`: 77 passed, 5 warnings.

## Deferred

The invoice-family Wave 2 physical SQL owner split is locally closed.

Remaining non-Workbench physical SQL owner split candidates include:

- `bank_detail`
- `bank_account_balance`
- `search`
- `workbench_relation`
- `cost_statistics`
- `tax_offset`
- `no_oa_bank_batch`
- `turnover_ledger`

Full PSCIP-L4 closure remains deferred until production or equivalent runtime evidence proves fresh reads, worker completion, freshness barriers, and performance behavior for every page-level read model.

No server SSH, production DB, production queue, readiness flag, worker replay, or secret access was used in this wave.
