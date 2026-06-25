# server-py:etc-business-batch-delete-fallback-audit

Date: 2026-06-25
Status: analysis-closed

## Goal

Audit the remaining ETC business-batch delete fallback path in `Application` and select the next smallest local implementation boundary.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc.py`
- `backend/src/fin_ops_platform/services/etc_business_batch_application_service.py`
- `backend/src/fin_ops_platform/services/etc_legacy_batch_delete_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `tests/test_etc_backend.py`
- CodeGraph context for business-batch delete, legacy delete service and route owner surfaces.

## Findings

`_handle_api_etc_business_batch_delete(...)` is still a broad `Application`-owned side-effect orchestration path. It currently owns:

- JSON body parsing and expected-version extraction;
- business batch lookup and idempotent missing-batch fallback;
- invoice/import-batch id collection;
- linked reconciliation task lookup;
- changed-month calculation;
- relation freshness preflight for submitted business batches;
- `EtcService.delete_business_batch(...)`;
- submitted business batch reset handling;
- summary relation cancellation;
- refreshed invoice relinking;
- canonical ETC invoice removal by import batch;
- reconciliation task tombstone/cleanup after business batch delete;
- refresh/persist side effects;
- HTTP success/error response mapping.

This is too much ownership for `server.py`.

The route owner `EtcBusinessBatchApiRoutes` already owns list/create/detail/source/import/draft/manual status mapping through `EtcBusinessBatchApplicationService`, but DELETE currently bypasses it and returns to `_handle_api_etc_business_batch_delete(...)` in `Application`.

The existing `EtcLegacyBatchDeleteService` handles non-business legacy batch delete flows. It is not the right owner for business-batch delete because it starts from legacy submission/import batch ids and has different repair semantics.

The existing `EtcBusinessBatchApplicationService` owns user-scope business-batch API operations. It could eventually expose a `delete_payload(...)`, but directly moving all current delete side effects into it would add too many unrelated dependencies at once: import service, relation preflight/cancel ports, cleanup service, changed-month providers and persistence events.

## Decision

Select the next local implementation boundary:

`server-py:etc-business-batch-delete-service-extraction`

The next slice should introduce a dedicated service, likely `EtcBusinessBatchDeleteService`, with explicit dependencies:

- `etc_service`;
- `import_service`;
- `reconciliation_task_service`;
- `cleanup_service`;
- `existing_etc_invoices_by_ids`;
- `etc_invoice_changed_months`;
- `link_etc_invoices_to_existing_invoices`;
- `assert_etc_summary_relation_write_precondition_for_batch`;
- `cancel_etc_summary_relations_for_batch`.

The service should return an explicit result containing:

- the existing ETC service delete result payload;
- refresh events/reasons or changed months;
- whether state persistence is required.

`Application._handle_api_etc_business_batch_delete(...)` should remain temporarily as a thin HTTP body/error/response mapper for this implementation slice. A later route callback collapse can move the thin mapper into `EtcBusinessBatchApiRoutes` or the business route owner.

## Stop Gates For Implementation

- Do not change business batch delete response shape.
- Do not change submitted reset semantics.
- Do not remove relation freshness preflight.
- Do not change summary relation cancellation semantics.
- Do not change canonical ETC invoice cleanup semantics.
- Do not change reconciliation task tombstone/cleanup semantics.
- Do not pass the whole `Application` into the new service.
- Do not perform production validation or mutation.

## Required Tests For Next Slice

- Add direct service tests covering at least:
  - unsubmitted/import-backed business batch delete removes canonical invoices and requests refresh/persist;
  - submitted business batch reset runs relation preflight/cancel and cleanup;
  - missing/stale business id fallback preserves idempotent delete behavior.
- Preserve existing API regressions in `tests/test_etc_backend.py`.
- Extend static Guard so `server.py` delegates delete side-effect orchestration to the new service while keeping HTTP mapping only.

## Verification

Analysis-only slice. No runtime code changed.

## Next Boundary

`server-py:etc-business-batch-delete-service-extraction`
