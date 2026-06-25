# server-py:etc-business-route-owner-local-closure-audit

**Status:** analysis-closed
**Date:** 2026-06-25
**Previous boundary:** `server-py:etc-business-oa-draft-revoke-route-callback-collapse`
**Next boundary:** `server-py:input-invoice-usage-oa-reverse-route-owner-audit`

## Goal

Audit ETC business-batch route-owner local implementation support after delete and OA draft revoke callback collapse.

## Findings

Local business-batch route-owner support is accounted for:

- `EtcBusinessBatchApiRoutes` owns list, create, detail, source files, import preview/confirm, OA draft create, OA draft revoke, manual OA status and business-batch DELETE mapping.
- `EtcBusinessBatchApplicationService` owns payload workflows and scoped actor mapping for list/create/detail/import/OA draft/manual status plus the new revoke payload boundary.
- `EtcBusinessBatchDeleteService` owns delete side-effect orchestration, relation freshness preflight, relation cancellation, reconciliation task cleanup and returned refresh/persist events.
- `server.py` no longer defines private callbacks:
  - `_handle_api_etc_business_batches`
  - `_handle_api_etc_business_batch_create`
  - `_route_api_etc_business_batch`
  - `_handle_api_etc_business_import_preview`
  - `_handle_api_etc_business_import_confirm`
  - `_handle_api_etc_business_oa_draft`
  - `_handle_api_etc_business_manual_oa_status`
  - `_handle_api_etc_business_batch_delete`
  - `_handle_api_etc_business_oa_draft_revoke`
- The remaining `server.py` business-batch functions are classified as:
  - `_etc_business_routes(...)`: dependency assembly.
  - `_handle_api_etc_business_batches_route(...)`: active root dispatch/session/body/response wrapper.
  - `_route_api_etc_business_batch_v2(...)`: active subroute dispatch/session/body/response wrapper.
  - `_handle_legacy_etc_batch_business_delete(...)`: legacy `/api/etc/batches/{id}` compatibility resolver.
  - `_delete_etc_business_batch_via_route_owner(...)`: route-owner response conversion helper for the legacy compatibility resolver.

## Decision

Mark this slice `analysis-closed` and treat ETC business-batch local route-owner support as accounted for. This is not full ETC module closure and not global modular IO closure.

Select `server-py:input-invoice-usage-oa-reverse-route-owner-audit` next because `server.py` still has a dense active handler group for input-invoice usage OA reverse flows:

- rows/filter/detail handlers;
- export handlers;
- payment-status rule handlers;
- OA reverse preview/create/history/staged drafts/one-step draft/batch get/draft create/draft revoke/status refresh/manual status handlers.

That group is larger and higher-risk than continuing inside ETC business-batch, where no private callback ownership gap remains.

## Verification

- Literal inventory:
  - `rg -n "def _handle_api_etc|def _route_api_etc|def _handle_legacy_etc|def _delete_etc_business|def _etc_.*routes" backend/src/fin_ops_platform/app/server.py`
  - `rg -n "def _handle_api_|def _route_api_" backend/src/fin_ops_platform/app/server.py`
- Existing Guard already prevents removed ETC business-batch callbacks from returning and requires route-owner delegation.

## Docs Impact

Only modular IO state files and ETC implementation notes need updates. Product/API long-term facts are unchanged.

## Remaining Risk

- Production browser/admin/write validation remains a final validation gate and was not run.
- ETC business-batch route-owner local closure does not close the whole ETC module, because legacy batch/reconciliation/import/invoice surfaces and production evidence still have separate accounting.
- `server.py` still has many non-ETC and non-business-batch module-specific handlers; continue with the selected input-invoice usage OA reverse audit.
