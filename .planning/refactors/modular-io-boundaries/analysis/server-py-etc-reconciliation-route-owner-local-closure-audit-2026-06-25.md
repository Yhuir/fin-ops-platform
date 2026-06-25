# server-py:etc-reconciliation-route-owner-local-closure-audit

Date: 2026-06-25
Status: analysis-closed

## Goal

Audit ETC reconciliation task route ownership after upload/text callback collapse and decide whether this area is locally closed.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for `EtcReconciliationTaskApiRoutes` and residual route/helper symbols.

## Findings

Local route callback migration is complete for this surface:

- `server.py` no longer defines any `_handle_api_etc_reconciliation*` callback.
- `EtcReconciliationTaskApiRoutes` owns task list/create/detail/delete/imported-invoice delete/source-file delete/item patch/confirm/reopen/refresh/upload/text dispatch and HTTP mapping.
- `EtcReconciliationSourceUploadService` owns source upload and ticket-root text store+parse+apply orchestration.
- `EtcReconciliationImportCleanupService` owns delete/import cleanup side effects.

However, ETC reconciliation route ownership is not locally closed yet. `server.py` still owns payload/read-shaping helpers injected into the route owner:

- `_etc_reconciliation_task_payload(...)`
- `_etc_reconciliation_unavailable_task_payload(...)`
- `_etc_reconciliation_import_blockers(...)`
- `_etc_reconciliation_imported_invoice_summary(...)`
- `_etc_reconciliation_task_can_confirm(...)`

These helpers are not simple dependency assembly. They encode response shape and route-facing task availability/confirmability semantics. Keeping them in `Application` means `server.py` still owns part of the ETC reconciliation route contract.

## Decision

Do not mark ETC reconciliation route-owner local closure.

Select the next boundary:

`server-py:etc-reconciliation-task-payload-facade-audit`

Scope:

- Audit the payload helper group and all callers.
- Decide whether to extract a dedicated payload facade/serializer service.
- Preserve existing task payload response shape, import blockers, imported invoice summary and `canConfirm` semantics.
- Do not change task mutation, source upload, import cleanup or business behavior.

## Verification

Analysis-only slice. No runtime code changed.

Additional local facts:

- `server.py` currently has `19408` lines.
- `server.py` has `180` `_handle_api_*` methods.
- `server.py` has `0` `_handle_api_etc_reconciliation*` methods.

## Next Boundary

`server-py:etc-reconciliation-task-payload-facade-audit`
