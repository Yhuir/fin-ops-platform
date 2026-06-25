# server-py:output-invoice-collection-mutation-route-callback-audit

Status: `analysis-closed`

Date: 2026-06-25

## Scope

Audit the remaining output invoice collection `Application` callbacks after read/export/status/history/detail route callback collapse.

This audit does not change runtime code and does not claim output invoice collection module/global closure.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py`
- `docs/modules/output-invoice-collections/README.md`
- `docs/modules/output-invoice-collections/state-machine.md`
- `docs/modules/output-invoice-collections/tests.md`
- `tests/test_output_invoice_collection_api.py`
- Prior analysis:
  - `server-py-output-invoice-collection-route-owner-audit-2026-06-25.md`
  - `server-py-output-invoice-collection-read-export-route-callback-collapse-2026-06-25.md`

CodeGraph context was used before the audit to inspect the remaining output collection mutation route surface.

## Remaining Callback Classification

| Callback | Classification | Notes |
| --- | --- | --- |
| `_handle_api_output_invoice_collections_receipt_preview(...)` | thin body/session/error/JSON wrapper | Business behavior already lives in `OutputInvoiceCollectionApiRoutes.receipt_preview(...)`, `OutputInvoiceCollectionReceiptService` and query service fallback. |
| `_handle_api_output_invoice_collections_collection_status(...)` | thin mutation wrapper | Delegates to `OutputInvoiceCollectionApiRoutes.set_collection_status(...)`; preserves `x-request-id` trace id. |
| `_handle_api_output_invoice_collections_collection_reminder(...)` | thin mutation wrapper | Delegates to `upsert_collection_reminder(...)`; preserves `x-request-id` trace id. |
| `_handle_api_output_invoice_collections_collection_reminder_delete(...)` | thin session/error/JSON wrapper | Delegates to `cancel_collection_reminder(...)`; preserves `x-request-id` trace id. |
| `_handle_api_output_invoice_collections_red_relation_create(...)` | thin mutation wrapper | Delegates to `confirm_red_invoice_relation(...)`; preserves `x-request-id` trace id. |
| `_handle_api_output_invoice_collections_red_relation_delete(...)` | thin session/error/JSON wrapper | Delegates to `revoke_red_invoice_relation(...)`; preserves `x-request-id` trace id. |
| `_handle_api_output_invoice_collections_receipt_create(...)` | thin mutation wrapper with idempotency header mapping | Delegates to `create_receipt(...)`; must preserve `Idempotency-Key` / `idempotency-key` fallback and `x-request-id`. |
| `_handle_api_output_invoice_collections_receipt_void(...)` | thin mutation wrapper | Delegates to `void_receipt(...)`; preserves `x-request-id`. |
| `_handle_api_output_invoice_collections_receipt_reissue(...)` | thin mutation wrapper | Delegates to `reissue_receipt(...)`; preserves `x-request-id`. |
| `_handle_api_output_invoice_collections_receipt_settings(...)` | thin admin read wrapper | Delegates to `get_receipt_settings(...)`; permission check is in route owner/service method. |
| `_handle_api_output_invoice_collections_receipt_settings_update(...)` | thin mutation wrapper | Delegates to `update_receipt_settings(...)`. |
| `_output_invoice_collection_mutation(...)` | shared body/session/error/JSON wrapper | Can move into route owner as a private HTTP helper if route owner receives a `load_json_body` port. |

## Finding

The remaining callbacks do not own lifecycle, receipt, red invoice relation, idempotency business rules or freshness target generation. Those responsibilities already live in `OutputInvoiceCollectionApiRoutes`, `OutputInvoiceCollectionLifecycleService` and `OutputInvoiceCollectionReceiptService`.

The next implementation slice can collapse the remaining mutation/receipt callbacks into `OutputInvoiceCollectionApiRoutes.route(...)` by adding an explicit body loader port and preserving:

- read/mutation permission behavior through the existing session resolver;
- structured error responses;
- `x-request-id` trace id propagation;
- `Idempotency-Key` / `idempotency-key` mapping for receipt create;
- receipt settings admin-only behavior;
- existing HTTP status and JSON response shapes.

SQL read-model fresh-gate helper extraction remains separate work and must not be mixed into the mutation callback collapse.

## Next Boundary

`server-py:output-invoice-collection-mutation-route-callback-collapse`

## Guard Expectations For Next Boundary

- Guard that remaining `_handle_api_output_invoice_collections*` callbacks are removed from `server.py`.
- Guard that `OutputInvoiceCollectionApiRoutes.route(...)` owns receipt preview/settings and lifecycle/receipt/red-relation mutation route markers.
- Preserve output collection API regression coverage for lifecycle writes, receipt create/void/reissue/history/settings, permission failures and structured errors.
- Do not change SQL fresh-gate helper behavior in the same slice.
