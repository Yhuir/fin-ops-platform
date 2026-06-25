# server-py:input-invoice-usage-oa-reverse-route-owner-audit

**Status:** analysis-closed
**Date:** 2026-06-25
**Previous boundary:** `server-py:etc-business-route-owner-local-closure-audit`
**Next boundary:** `server-py:input-invoice-usage-oa-reverse-route-owner-facade-extraction`

## Goal

Audit the active input-invoice usage OA reverse handler group in `server.py` and select the next narrow local implementation boundary.

## Current Ownership

`server.py` still owns URL dispatch plus HTTP/session/body/error mapping for `/api/input-invoice-usage/oa-reverse*`:

- `POST /api/input-invoice-usage/oa-reverse/preview`
- `GET /api/input-invoice-usage/oa-reverse/staged-drafts`
- `GET /api/input-invoice-usage/oa-reverse/submitted-history`
- `POST /api/input-invoice-usage/oa-reverse/oa-draft`
- `POST /api/input-invoice-usage/oa-reverse/batches`
- `GET /api/input-invoice-usage/oa-reverse/batches/{batch_id}`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft/revoke`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-status/refresh`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/manual-oa-status`

The business state machine is already in `InputInvoiceUsageOaReverseService`. The route layer should not reimplement preview hash, draft, revoke, status refresh, manual status, relation write, audit, invalidation or repository behavior.

## Evidence

- `InputInvoiceUsageOaReverseService` owns batch state, idempotency, version conflict, OA draft/revoke, evidence detection, manual status and read model invalidation callbacks.
- `TargetOaApplicantTokenProvider` owns target applicant OA draft client creation.
- `server.py` currently holds reusable helper ports:
  - `_input_invoice_usage_mutation_actor(...)`
  - `_input_invoice_usage_oa_reverse_error_response(...)`
  - `_input_invoice_usage_oa_draft_client_for_batch(...)`
  - `_target_oa_applicant_token_provider()`
- Module docs require OA reverse draft creation to use target applicant credentials, not current request token, and require local revoke to clear only FinOps state, not delete external OA drafts.
- Existing tests cover service, API and frontend OA reverse flows.

## Decision

Select `server-py:input-invoice-usage-oa-reverse-route-owner-facade-extraction`.

The first implementation slice should:

- add `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`;
- define `InputInvoiceUsageOaReverseApiRoutes` with explicit ports, not `Application`;
- move route-owner dispatch and the lighter HTTP mapping paths first:
  - preview;
  - submitted history;
  - staged drafts;
  - batch create;
  - batch get;
- keep OA draft create/revoke/status refresh/manual status in `Application` for a follow-up slice because they additionally require target applicant draft-client/provider and write-after-read operation-barrier/UI-sensitive behavior;
- keep rows/filter-options/export/read-model routes out of this boundary.

## Tests To Run Next

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_input_invoice_usage_api.py`
- targeted API regressions from `tests/test_input_invoice_usage_api.py` that cover preview, batch create/get, staged drafts and submitted history;
- a static Guard proving `server.py` delegates OA reverse route dispatch to the route owner and does not pass `Application`;
- `bash scripts/verify.sh docs`;
- `git diff --check`.

## Stop Gates

- Do not change OA reverse response shape, status codes, permission behavior, idempotency, version conflict or read model invalidation.
- Do not move OA token/header parsing into business services.
- Do not pass the whole `Application` into a route owner or service.
- Do not touch rows/filter-options/export/read-model fresh gates in this slice.
- Do not run production browser/admin/write validation.

## Docs Impact

Update input-invoice-usage implementation notes and modular IO state files. Long-term product/API facts remain unchanged unless behavior changes, which this audit rejects.
