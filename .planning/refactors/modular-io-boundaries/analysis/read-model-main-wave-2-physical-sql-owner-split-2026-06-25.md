# Read Model Main Closure Wave 2 Physical SQL Owner Split

Date: 2026-06-25

Branch: `main`

Backup branch: `codex/backup-main-before-read-model-closure-20260625-230543`

Controller: `.planning/refactors/modular-io-boundaries/prompts/07-read-model-main-closure-controller.md`

## Scope Completed In This Wave

This wave completed the first physical SQL owner split inside the invoice-family read models:

- `input_invoice_usage`
- `output_invoice_collection`
- `oa_pending_payment`

The public narrow ports remain unchanged:

- `InputInvoiceUsageReadModelRepositoryPort`
- `OutputInvoiceCollectionReadModelRepositoryPort`
- `OaPendingPaymentReadModelRepositoryPort`

`PostgresReadModelRepository` now keeps compatibility methods for existing port contracts, but those methods delegate to `PostgresInvoiceUsageCollectionReadModelRepository`. The new owner contains the physical SQL for list/detail/save/mark/prune behavior for the selected family.

## PSCIP Movement

Before this wave, these three read models were already:

- Partitioned by month-like scope keys through existing scope policy and repository contracts.
- Scoped through read model scope tables and `scope_key` filters.
- Incrementally projected through durable queue events and scoped projection writes.

The gap was ownership: narrow ports wrapped broad shared repository methods whose physical SQL remained inside `PostgresReadModelRepository`.

After this wave:

- `input_invoice_usage`, `output_invoice_collection`, and `oa_pending_payment` move from `PSCIP-L3-local-contract` toward `PSCIP-L3-local-owner-split`.
- No PSCIP-L4 closure is claimed because no production or equivalent runtime evidence was collected.
- No Redis or RabbitMQ freshness source was introduced.
- No broad `all` fake-fresh path was introduced.
- Dirty scope/outbox ownership remains unchanged.

## Guard Added

`tests/test_read_model_manifest.py` now includes `test_invoice_usage_collection_physical_sql_owner_is_split_from_shared_repository`.

The guard proves:

- The selected family methods exist on `PostgresInvoiceUsageCollectionReadModelRepository`.
- `PostgresReadModelRepository` compatibility methods delegate through `_invoice_usage_collection_repository`.
- The shared compatibility methods do not directly reference:
  - `read_model.input_invoice_usage_rows`
  - `read_model.output_invoice_collection_rows`
  - `read_model.oa_pending_payment_rows`

## Verification

Commands run:

```bash
python3 -m py_compile backend/src/fin_ops_platform/services/postgres_repositories/read_models.py
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_manifest tests.test_runtime_worker_registry -v
PYTHONPATH=backend/src python3 -m unittest tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards -v
PYTHONPATH=backend/src python3 -m pytest tests/test_invoice_usage_collection_sql_runtime.py tests/test_oa_pending_payment_api.py -q
```

Results:

- `tests.test_read_model_manifest`: passed.
- `tests.test_read_model_manifest tests.test_runtime_worker_registry`: passed.
- `tests.test_read_model_architecture_guards tests.test_platform_runtime_boundary_guards`: passed.
- `tests/test_invoice_usage_collection_sql_runtime.py tests/test_oa_pending_payment_api.py`: 67 passed, 5 warnings, 5 subtests passed.

## Deferred

The rest of the Wave 2 physical SQL owner split remains open:

- `pending_invoice`
- `invoice_lifecycle`

Full PSCIP-L4 closure remains deferred until production or equivalent runtime evidence proves fresh reads, worker completion, freshness barriers, and performance behavior for every page-level read model.

No server SSH, production DB, production queue, readiness flag, worker replay, or secret access was used in this wave.
