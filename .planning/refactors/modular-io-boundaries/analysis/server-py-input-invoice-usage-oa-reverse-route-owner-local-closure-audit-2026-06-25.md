# server-py:input-invoice-usage-oa-reverse-route-owner-local-closure-audit

Status: `analysis-closed`

## Scope

This audit checked whether the input-invoice usage OA reverse route-owner surface is locally accounted for after:

- `server-py:input-invoice-usage-oa-reverse-route-owner-facade-extraction`
- `server-py:input-invoice-usage-oa-reverse-draft-mutation-route-callback-collapse`

Rows, filter-options, export, detail and payment-status-rule routes are outside this OA reverse sub-boundary.

## Evidence

- `InputInvoiceUsageOaReverseApiRoutes` owns all `/api/input-invoice-usage/oa-reverse*` HTTP mapping:
  - preview;
  - submitted history;
  - staged drafts;
  - batch create;
  - batch get;
  - one-step draft create;
  - batch draft create;
  - draft revoke;
  - status refresh;
  - manual OA status.
- `server.py` has no remaining `def _handle_api_input_invoice_usage_oa_reverse_*` handlers.
- `Application._input_invoice_usage_oa_reverse_routes(...)` is dependency assembly only.
- Remaining OA reverse related `Application` methods are explicit platform/helper ports:
  - `_input_invoice_usage_oa_reverse_service(...)` creates the service and repository/evidence/relation/audit/read-model dependencies.
  - `_record_input_invoice_usage_oa_reverse_audit(...)` adapts the audit service.
  - `_invalidate_input_invoice_usage_oa_reverse_read_models(...)` adapts read model refresh and pair relation persistence.
  - `_input_invoice_usage_oa_draft_client_for_batch(...)` adapts target applicant credential/OA draft client lookup.
  - `_input_invoice_usage_mutation_actor(...)` adapts OA session and mutation permission.
  - `_input_invoice_usage_oa_reverse_error_response(...)` maps service/command errors to HTTP responses.
- `InputInvoiceUsageOaReverseService` remains the business owner for preview, batch state, idempotency, version conflicts, draft/revoke/status/manual decisions, relation command writes, audit and read model invalidation.
- Static Guard coverage in `test_input_invoice_oa_reverse_routes_use_route_owner` prevents the removed handlers from returning and checks explicit route-owner ports.

## Closure Decision

OA reverse route-owner local support is accounted for.

This does not close the whole input-invoice-usage module or global modular refactor. Real production OA login, target applicant credentials, worker/App Status convergence, browser/admin/write evidence and broad high-row validation remain final validation gates.

## Selected Next Boundary

`server-py:input-invoice-usage-core-route-owner-audit`

Audit the remaining non-OA-reverse input-invoice usage HTTP handlers still owned by `Application`:

- rows;
- filter-options;
- export preview/export;
- invoice/bank/OA detail;
- relation details;
- payment-status rules get/update.

The audit must not change rows/filter/export/read-model fresh gates. It should classify whether a route owner can safely own HTTP mapping while retaining read model fresh-gate services and repository ports as explicit dependencies.

## Verification

Analysis-only slice. Evidence was collected from:

- CodeGraph context for `InputInvoiceUsageOaReverseApiRoutes` and `Application._input_invoice_usage_oa_reverse_routes(...)`;
- targeted `rg` scan for `input_invoice_usage_oa_reverse` route handlers;
- source inspection of `server.py`, `routes_input_invoice_usage_oa_reverse.py`, `input_invoice_usage_oa_reverse_service.py` and static Guard tests.

No runtime code changed in this audit slice.
