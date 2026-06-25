# Next Prompt

Continue after `server-py:etc-reconciliation-ticket-root-text-service-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-ticket-root-text-service-extraction`.
- Row330 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-ticket-root-text-service-extraction-2026-06-25.md`.
- Generic source upload and ticket-root text persistence/parser orchestration now live in `EtcReconciliationSourceUploadService`.
- `Application._handle_api_etc_reconciliation_upload(...)` and `_handle_api_etc_reconciliation_ticket_root_texts(...)` are thin HTTP wrappers.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-upload-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-ticket-root-text-service-extraction-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` `_etc_reconciliation_routes(...)`, `_handle_api_etc_reconciliation_upload(...)`, `_handle_api_etc_reconciliation_ticket_root_texts(...)`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_source_upload_service.py`
   - targeted source upload and ticket-root text tests
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect route owner and remaining callback wiring.
4. Implement only upload route callback collapse:
   - inject `source_upload_service` into `EtcReconciliationTaskApiRoutes`;
   - move the thin generic upload and ticket-root text HTTP mapping into the route owner;
   - remove `_handle_api_etc_reconciliation_upload(...)` and `_handle_api_etc_reconciliation_ticket_root_texts(...)` from `server.py`;
   - preserve error codes/messages and task payload shape.
5. Update static Guard and targeted API regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not move unrelated ETC import or legacy batch routes.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owner or service.
- Preserve source upload and ticket-root text response shapes, storage error mapping and parser behavior.
