# server-py:output-invoice-collection-route-owner-audit

Status: `analysis-closed`

Date: 2026-06-25

## Scope

Audit output invoice collection route ownership in `Application` and select the next bounded local implementation slice.

This audit does not change runtime code and does not claim output invoice collection module/global closure.

## Evidence Reviewed

- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/output-invoice-collections/state-machine.md`
- `docs/modules/output-invoice-collections/tests.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
- `tests/test_output_invoice_collection_api.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph context was used before the audit to inspect `OutputInvoiceCollectionApiRoutes` and related server callbacks.

## Current Route Shape

`OutputInvoiceCollectionApiRoutes` already owns domain-facing route methods for:

- rows and filter-options;
- export preview and export workbook payload;
- status rules;
- invoice/bank/relation details;
- receipt preview/history/settings;
- collection status and reminders;
- red invoice relation create/delete;
- receipt create/void/reissue.

`Application` still owns direct dispatch branches under `/api/output-invoice-collections*` and many `_handle_api_output_invoice_collections*` wrappers.

## Callback Classification

| Callback group | Classification | Notes |
| --- | --- | --- |
| Rows/filter-options/export-preview/export/status-rules/invoice detail/bank detail/relation details/receipt history | thin HTTP/session/response wrappers | These call route-owner methods, map `OutputInvoiceCollectionError`, and return JSON/XLSX. They are good first callback-collapse candidates. |
| Receipt preview | thin body/session/response wrapper, but POST read/preview semantics | Can likely move with read/export group or a follow-up small slice. Keep out of first implementation slice if the first slice is already broad. |
| Collection status, collection reminder upsert/delete, red relation create/delete, receipt create/void/reissue, receipt settings update | mutation wrappers | Business behavior is in route owner plus lifecycle/receipt services, but HTTP idempotency key, trace id and body/session mapping should be migrated separately after read/export callback collapse. |
| `_output_invoice_collection_mutation(...)` | shared mutation HTTP wrapper | Should not be deleted until all mutation callbacks move or an equivalent route-owner route method owns body/session/error mapping. |
| `_get_output_invoice_collection_rows_from_sql_read_model(...)`, `_get_output_invoice_collection_all_rows_from_sql_read_model(...)`, `_get_output_invoice_collection_relation_details_from_sql_read_model(...)`, `_output_invoice_collection_sql_payload_requires_schema_refresh(...)`, `_output_invoice_collection_expected_source_versions(...)` | fresh-gate implementation/provider surface | This mirrors the prior input usage fresh-gate gap but is not part of the first route callback collapse. It should be audited/extracted after route callback ownership is narrowed. |

## Finding

The first safe implementation boundary is not a full output collection migration. Output collection combines read routes, export, lifecycle writes, receipt lifecycle and fresh-gate logic. A single implementation slice across all of these would be too broad.

The next slice should collapse only read/export/status/history route callbacks into `OutputInvoiceCollectionApiRoutes` with explicit HTTP/platform ports:

- `/api/output-invoice-collections/rows`
- `/api/output-invoice-collections/filter-options`
- `/api/output-invoice-collections/export-preview`
- `/api/output-invoice-collections/export`
- `/api/output-invoice-collections/status-rules`
- `/api/output-invoice-collections/receipts/history`
- `/api/output-invoice-collections/invoices/{invoice_id}/detail`
- `/api/output-invoice-collections/bank-transactions/{bank_transaction_id}/detail`
- `/api/output-invoice-collections/rows/{row_id}/relation-details`

Receipt preview and write routes should remain for a later slice unless implementation proves the first read/export migration is still narrow.

## Next Boundary

`server-py:output-invoice-collection-read-export-route-callback-collapse`

## Guard Expectations For Next Boundary

- Add or update static guard coverage so the migrated read/export callbacks do not return to `server.py`.
- Preserve current output collection API response shape, status codes and XLSX headers.
- Preserve relation-detail `202` refreshing semantics.
- Preserve output collection fresh-gate behavior; do not extract fresh gate in the same slice.
- Run targeted output collection API regressions and route-owner guard tests.
