# Read Model And Worker Matrix

**Purpose:** Give page phases a single baseline for read model, worker, App Status, and stale/fresh ownership.

## Governing Contracts

- Read model queries must go through freshness/status/enqueue boundaries.
- Refresh requests must pass through scope policy / refresh gateway / durable queue boundaries.
- Durable truth is PostgreSQL `job.outbox_events` and `job.read_model_dirty_scopes`.
- Redis can cache only fresh payloads after the fresh gate.
- RabbitMQ is wakeup/transport only, not readiness truth.
- Workers must not depend on HTTP request/session/Application state.
- App Status reads registries and runtime facts; pages do not write global status.

## App Status Domain Matrix

| Page/domain | Route | Read model keys | Worker instances | Job/dependency signals |
| --- | --- | --- | --- | --- |
| `workbench` / 关联台 | `/` | `workbench`, `workbench_relation` | `workbench`, `workbench-relation`, `workbench-matching` | `workbench_rebuild`, `workbench_read_model_rebuild`, `oa_sync_workbench_rebuild`, `workbench_matching`, dependency `oa_sync` |
| `imports_bank_transactions` | `/imports/bank-transactions` | none directly | `import` | `file_import`, `bank_transaction_import`, `import.process.requested` |
| `imports_invoices` | `/imports/invoices` | none directly | `import` | `file_import`, `invoice_import`, `import.process.requested` |
| `imports_etc_invoices` | `/imports/etc-invoices` | none directly | `import` | `etc_invoice_import`, `file_import`, `import.process.requested` |
| `tax_offset` | `/tax-offset` | `tax_offset`, `invoice_lifecycle` | `tax-offset`, `invoice-lifecycle`, `invoice-lifecycle-secondary` | `tax_offset.read_model.refresh`, `invoice_lifecycle.read_model.refresh`, `tax_certified_import` |
| `cost_statistics` | `/cost-statistics` | `cost_statistics` | `cost-statistics` | `cost_statistics.read_model.refresh`, `cost_statistics_cache_warmup` |
| `bank_details` | `/bank-details` | `bank_detail`, `bank_account_balance` | `bank-detail`, `bank-account-balance` | `bank_detail.read_model.refresh`, `bank_account_balance.read_model.refresh`, `bank_transaction_import` |
| `pending_invoices` | `/pending-invoices` | `pending_invoice`, `search`, `invoice_lifecycle` | `pending-invoice`, `search`, `invoice-lifecycle`, `invoice-lifecycle-secondary` | `pending_invoice.read_model.refresh`, `search.read_model.refresh`, `invoice_lifecycle.read_model.refresh` |
| `input_invoice_usage` | `/input-invoice-usage` | `input_invoice_usage`, `invoice_lifecycle` | `invoice-usage-collection`, `invoice-lifecycle`, `invoice-lifecycle-secondary` | `input_invoice_usage.read_model.refresh`, `invoice_lifecycle.read_model.refresh` |
| `oa_pending_payments` | `/oa-pending-payments` | `oa_pending_payment`, `invoice_lifecycle` | `invoice-usage-collection`, `invoice-lifecycle`, `invoice-lifecycle-secondary`, `oa-sync` | `oa_pending_payment.read_model.refresh`, `invoice_lifecycle.read_model.refresh`, `oa.sync`, dependency `oa_sync` |
| `output_invoice_collections` | `/output-invoice-collections` | `output_invoice_collection`, `invoice_lifecycle` | `invoice-usage-collection`, `invoice-lifecycle`, `invoice-lifecycle-secondary` | `output_invoice_collection.read_model.refresh`, `invoice_lifecycle.read_model.refresh` |
| `no_oa_bank_batches` | `/no-oa-bank-batches` | `no_oa_bank_batch` | `no-oa-bank-batch` | `no_oa_bank_batch.read_model.refresh` |
| `batch_accounting` | `/batch-accounting` | `workbench_relation` | `workbench-relation` | `workbench_relation.read_model.refresh` |
| `turnover_ledger` | `/turnover-ledger` | `turnover_ledger` | `turnover-ledger` | `turnover_ledger.read_model.refresh` |
| `etc_tickets` | `/etc-tickets` | none directly in App Status registry | `import` | `etc_invoice_import`; downstream Workbench/tax/cost readiness still matters |
| `settings` | `/settings` | none directly | `oa-sync` | `oa.sync`, `settings_refresh`, dependencies `oa_identity`, `state_store` |
| `app_health_operations` | `/operations/app-health` | all observed domains indirectly | `oa-sync`, `workbench`, `bank-detail`, `import` | dependencies `background_jobs`, `state_store` plus runtime registries |

## Read Model Registry Matrix

| Read model key | Scope type | Worker | Refresh event | Readiness strategy |
| --- | --- | --- | --- | --- |
| `workbench` | `workbench` | `workbench` | `workbench.read_model.refresh` | active generation |
| `workbench_relation` | `workbench_relation` | `workbench-relation` | `workbench_relation.read_model.refresh` | app status readiness |
| `bank_detail` | `bank_detail` | `bank-detail` | `bank_detail.read_model.refresh` | app status readiness |
| `bank_account_balance` | `bank_account_balance` | `bank-account-balance` | `bank_account_balance.read_model.refresh` | app status readiness |
| `pending_invoice` | `pending_invoice` | `pending-invoice` | `pending_invoice.read_model.refresh` | app status readiness |
| `search` | `search` | `search` | `search.read_model.refresh` | app status readiness |
| `invoice_lifecycle` | `invoice_lifecycle` | `invoice-lifecycle` | `invoice_lifecycle.read_model.refresh` | app status readiness |
| `input_invoice_usage` | `input_invoice_usage` | `invoice-usage-collection` | `input_invoice_usage.read_model.refresh` | app status readiness |
| `output_invoice_collection` | `output_invoice_collection` | `invoice-usage-collection` | `output_invoice_collection.read_model.refresh` | app status readiness |
| `oa_pending_payment` | `oa_pending_payment` | `invoice-usage-collection` | `oa_pending_payment.read_model.refresh` | app status readiness |
| `cost_statistics` | `cost_statistics` | `cost-statistics` | `cost_statistics.read_model.refresh` | app status readiness |
| `tax_offset` | `tax_offset` | `tax-offset` | `tax_offset.read_model.refresh` | app status readiness |
| `no_oa_bank_batch` | `no_oa_bank_batch` | `no-oa-bank-batch` | `no_oa_bank_batch.read_model.refresh` | app status readiness |
| `turnover_ledger` | `turnover_ledger` | `turnover-ledger` | `turnover_ledger.read_model.refresh` | app status readiness |

## Compatibility / Transitional Workers

| Worker | Current role | Page-phase rule |
| --- | --- | --- |
| `search-pending` | Compatibility worker handling `search` and `pending_invoice` refresh events. | Do not add new coupling. If touched, verify registry/runtime compatibility and migration plan. |
| `cost-tax` | Compatibility worker handling `cost_statistics` and `tax_offset` refresh events. | Do not rely on it as the canonical worker; focused `cost-statistics` and `tax-offset` workers are present. |
| `invoice-lifecycle-secondary` | Secondary invoice lifecycle worker. | Treat as scaling/availability member; canonical read model key remains `invoice_lifecycle`. |
| `search-secondary` / `search-tertiary` | Additional search workers. | Treat as runtime capacity members; canonical read model key remains `search`. |

## Scope Policy Notes

- `cost_statistics` has a dedicated scope policy and normalizes legacy raw `all` / month values into canonical cost statistics scope keys.
- `no_oa_bank_batch` accepts month-or-`all` scope keys through a dedicated policy.
- Other scope types use generic non-empty validation unless a page phase discovers stricter contract docs or code.

## Page Phase Questions

Before changing read behavior:

- Which read model key and scope type does this page depend on?
- Does the page require `fresh`, tolerate `refreshing`, or show stale diagnostics?
- Does the backend enqueue refresh on miss/stale/source mismatch?
- Does the frontend distinguish empty fresh payload from missing/stale payload?
- Does App Status expose the same blocker that the page sees locally?

Before changing write behavior:

- Which refresh events are enqueued?
- Which worker instances must be running?
- Which scopes are returned to the frontend?
- Does operation barrier wait on the right target scopes?
- Are stale/fresh failures visible and actionable?
