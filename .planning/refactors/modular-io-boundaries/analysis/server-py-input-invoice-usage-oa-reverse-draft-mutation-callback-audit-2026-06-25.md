# server-py:input-invoice-usage-oa-reverse-draft-mutation-callback-audit

Status: `analysis-closed`

## Scope

This audit reviewed the remaining input-invoice usage OA reverse mutation callbacks still owned by `Application` after the lightweight route-owner extraction:

- `POST /api/input-invoice-usage/oa-reverse/oa-draft`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft/revoke`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-status/refresh`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/manual-oa-status`

Rows, filter-options, export and read-model freshness gates remain out of scope.

## Findings

- The business state machine is already service-owned by `InputInvoiceUsageOaReverseService`.
- `create_oa_draft_from_selection(...)` owns one-step create semantics: preview replay, stale preview detection, batch create, draft create and target applicant OA client provider usage.
- `create_oa_draft(...)` owns batch draft creation, idempotency replay, version conflict, OA client call, draft-failed persistence, audit and read model invalidation.
- `revoke_oa_draft(...)` owns revoke transition rules, idempotency, audit and read model invalidation.
- `refresh_oa_status(...)` owns OA evidence detection, relation command write through `WorkbenchInputInvoiceUsageOaReverseRelationWriter`, audit and read model invalidation.
- `manual_oa_status(...)` owns submitted/not-submitted decisions, fallback status policy, idempotency, audit and read model invalidation.
- `Application` currently owns only HTTP/session/body mapping plus three explicit runtime seams:
  - `_target_oa_applicant_token_provider(...)`
  - `_input_invoice_usage_oa_draft_client_for_batch(...)`
  - `_int_or_none(...)`

## Selected Next Boundary

`server-py:input-invoice-usage-oa-reverse-draft-mutation-route-callback-collapse`

Move the five remaining mutation HTTP callbacks into `InputInvoiceUsageOaReverseApiRoutes` using explicit ports:

- `target_oa_applicant_token_provider`
- `oa_draft_client_for_batch`
- `int_or_none`
- existing `mutation_actor`
- existing `load_json_body`
- existing `json_response`
- existing `oa_reverse_error_response`

`Application` should remain responsible only for dependency assembly and retained platform helpers. The route owner must still not receive the whole `Application`.

## Required Guard/Test Evidence

- Extend `test_input_invoice_oa_reverse_lightweight_routes_use_route_owner` or add a new guard proving:
  - all five mutation route paths dispatch through `InputInvoiceUsageOaReverseApiRoutes`;
  - the five legacy `_handle_api_input_invoice_usage_oa_reverse_*` mutation handlers are removed from `server.py`;
  - route-owner constructor ports are explicit and do not include `Application`;
  - service methods remain the business owners.
- Re-run targeted OA reverse API regressions for one-step draft, batch draft, revoke/not-submitted/manual status, status refresh conflict and credential error.

## Stop Gates

- Do not change OA reverse response shape, status codes, permission behavior, idempotency, version conflict or read model invalidation.
- Do not move OA token/header parsing into services.
- Do not pass the whole `Application` into route owner or services.
- Do not touch rows/filter-options/export/read-model fresh gates.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.

## Verification

Analysis-only slice. Source inspection used CodeGraph context and targeted source reads:

- `Application` remaining OA reverse mutation handlers in `backend/src/fin_ops_platform/app/server.py`
- `InputInvoiceUsageOaReverseApiRoutes` in `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`
- `InputInvoiceUsageOaReverseService` mutation methods in `backend/src/fin_ops_platform/services/input_invoice_usage_oa_reverse_service.py`
- OA reverse API regressions in `tests/test_input_invoice_usage_api.py`
- platform static Guard in `tests/test_platform_runtime_boundary_guards.py`

No runtime code changed in this audit slice.
