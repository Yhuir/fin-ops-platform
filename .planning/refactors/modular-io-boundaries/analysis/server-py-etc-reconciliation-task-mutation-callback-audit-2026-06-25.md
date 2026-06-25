# server-py:etc-reconciliation-task-mutation-callback-audit

## Status

`analysis-closed`

## Goal

Audit the residual `Application` callbacks still injected into `EtcReconciliationTaskApiRoutes` and select the next safe local implementation boundary.

## Evidence Reviewed

- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Findings

`EtcReconciliationTaskApiRoutes` already owns route parsing for `/api/etc/reconciliation-tasks*`, root list/create/detail, task delete, and imported-invoices delete. It still receives these app-owned callbacks:

- `upload_source=self._handle_api_etc_reconciliation_upload`
- `upload_supplement_for_card=self._handle_api_etc_reconciliation_supplement_for_card_upload`
- `submit_ticket_root_texts=self._handle_api_etc_reconciliation_ticket_root_texts`
- `delete_source_file=self._handle_api_etc_reconciliation_source_file_delete`
- `patch_item=self._handle_api_etc_reconciliation_item_patch`
- `confirm_task=self._handle_api_etc_reconciliation_confirm`
- `reopen_task=self._handle_api_etc_reconciliation_reopen`
- `refresh_matches=self._handle_api_etc_reconciliation_refresh_matches`

These callbacks split into two risk groups:

1. Simple task mutation HTTP mapping:
   - source file delete
   - item patch
   - confirm
   - reopen
   - refresh matches

   These primarily parse JSON/expected version, call `EtcReconciliationTaskService`, map `KeyError`/`ValueError` to HTTP responses and serialize task payloads. They can move into the route owner using existing ports without changing business behavior.

2. Upload and parser-heavy flows:
   - credit-card/ticket-root/supplement source upload
   - supplement-for-card upload
   - ticket-root text submission

   These include multipart parsing, object-storage failure mapping, source mode detection, wrong-slot detection, parser selection, text decoding, and source-file persistence. Moving them together with simple mutations would be too broad for one safe slice. They should be audited separately and likely extracted behind an upload/parser application service or moved in smaller route-owner slices after the simple mutation callbacks are closed.

## Decision

Select a narrow implementation boundary:

`server-py:etc-reconciliation-simple-mutation-callback-collapse`

Scope:
- Move `delete_source_file`, `patch_item`, `confirm_task`, `reopen_task`, and `refresh_matches` HTTP callback bodies into `EtcReconciliationTaskApiRoutes`.
- Remove corresponding `_handle_api_etc_reconciliation_*` methods from `server.py`.
- Keep upload/source parser callbacks unchanged for the next audit.
- Add/update static guard coverage so simple mutation callbacks cannot return to `server.py`.
- Preserve existing API response shapes and targeted ETC reconciliation task regressions.

## Verification

Analysis-only slice. No runtime code changed.

## Next Boundary

`server-py:etc-reconciliation-simple-mutation-callback-collapse`
