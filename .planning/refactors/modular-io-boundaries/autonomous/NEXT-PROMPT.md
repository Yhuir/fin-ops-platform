# Next Prompt

Continue after `server-py:etc-reconciliation-source-upload-parser-boundary-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-source-upload-parser-boundary-audit`.
- Row327 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-source-upload-parser-boundary-audit-2026-06-25.md`.
- Row327 found generic source upload still owns store+parse+apply orchestration plus ticket-root wrong-slot/source-mode/content-type policy in `Application`.
- Directly moving generic source upload into `EtcReconciliationTaskApiRoutes` is rejected because it would move parser policy into the route owner.
- Ticket-root text submission remains a separate boundary.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-source-upload-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-source-upload-parser-boundary-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` `_handle_api_etc_reconciliation_upload(...)` and ticket-root helper functions
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
   - `backend/src/fin_ops_platform/services/etc_document_parsers.py`
   - targeted source upload tests in `tests/test_etc_backend.py`
   - service tests in `tests/test_etc_reconciliation_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect source upload service candidates, parser classes, `EtcReconciliationTaskService.store_uploaded_source_file(...)`, `apply_parse_result(...)` and route-owner wiring.
4. Implement only source upload service extraction:
   - add an explicit service/facade boundary for credit-card statement, ticket-root file and task-level supplement evidence uploads;
   - move store+parse+apply orchestration and ticket-root source-mode/wrong-slot/content-type policy out of `Application`;
   - keep route owner HTTP/multipart/error mapping thin;
   - do not move ticket-root text submission in this slice;
   - preserve error codes/messages and parser behavior.
5. Update static Guard and targeted regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not pass `Application` into the new service.
- Do not move ticket-root text submission in this slice.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Preserve object-storage error mapping, wrong-slot validation, ticket-root source-mode conflict behavior, parser output shape, content-type behavior and supplement parse behavior.
