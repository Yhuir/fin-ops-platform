# Output Invoice Collection Read Model Redesign Analysis

Date: 2026-07-01

## Scope

- Module: `output-invoice-collections`
- Direct read model: `output_invoice_collection`
- Upstream facts: formal output invoices, bank transactions, `workbench_relation`
- Worker path: `invoice-usage-collection` -> `InvoiceUsageCollectionSqlProjectionBuilder.rebuild_output_invoice_collection_read_model_scope(...)`

## Current Flow

1. `InvoiceUsageCollectionSqlProjectionBuilder.rebuild_output_invoice_collection_read_model_scope(scope)` delegates row construction to `OutputInvoiceCollectionQueryService._filtered_sorted_rows(...)`.
2. `OutputInvoiceCollectionQueryService._build_rows(...)` builds one row per invoice identity group, then attaches `workbench_relation` OA/bank/invoice summaries.
3. The frontend uses `invoiceRelations` as the displayed invoice cell when `relationCount > 1`.

## Finding

The current row owner is the invoice identity group. For a workbench relation that links one bank inflow to multiple output invoices, every member invoice can become an output-collection row while each row repeats the same relation-level invoice summary.

That produces the observed duplicate relation display: the same 364800 group can be rendered more than once. It also lets the visible invoice summary drift from the actual relation membership when the relation-level output invoice list is incomplete or stale.

## Target Boundary

- Row owner: linked output-invoice relation group when a `workbench_relation` contains multiple output invoices.
- Fallback row owner: existing invoice identity group when no multi-output relation exists.
- Input I/O: output invoice facts + bank facts + freshness-gated `workbench_relation`.
- Output I/O: one `output_invoice_collection` row per linked multi-output relation group, with `invoiceRelations.summaries` containing every output invoice member including negative/red invoices.
- Worker/read model: reuse the existing `invoice-usage-collection` worker and repository; bump `OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION` because row grouping and amount semantics change.

## Acceptance

- A linked group with `+182400, -182400, +182400` and one `182400` inflow emits one row, not duplicate rows.
- The row has `invoiceRelations.relationCount == 3`.
- The row net invoice total is `182400.00`.
- The negative invoice appears in relation summaries.
- Collection status is collected when linked inflow equals the net invoice total.

## Implementation Result

- `OutputInvoiceCollectionQueryService` now builds relation-group rows before invoice-identity fallback rows.
- `OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION` is `output-invoice-collections:v4-relation-group-rows`.
- Regression coverage: `test_multi_output_relation_emits_single_net_collection_row`.
- Docs updated: output module README, boundary I/O, state machine, test matrix, API contract, and read model boundary contract.
