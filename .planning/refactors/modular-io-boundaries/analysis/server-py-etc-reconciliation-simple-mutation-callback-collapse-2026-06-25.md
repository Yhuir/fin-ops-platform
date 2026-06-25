# server-py:etc-reconciliation-simple-mutation-callback-collapse

## Status

`local-implementation-closed`

## Goal

Move the simple ETC reconciliation task mutation HTTP callbacks from `Application` into `EtcReconciliationTaskApiRoutes`, while leaving upload/parser-heavy callbacks for a later boundary.

## Evidence Reviewed

- `analysis/server-py-etc-reconciliation-task-mutation-callback-audit-2026-06-25.md`
- `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_platform_runtime_boundary_guards.py`
- Targeted reconciliation task tests in `tests/test_etc_backend.py`

## Implementation

- Moved these HTTP callback bodies into `EtcReconciliationTaskApiRoutes`:
  - source-file delete
  - item patch
  - confirm
  - reopen
  - refresh matches
- Removed the corresponding app-owned callbacks from `server.py`:
  - `_handle_api_etc_reconciliation_source_file_delete`
  - `_handle_api_etc_reconciliation_item_patch`
  - `_handle_api_etc_reconciliation_confirm`
  - `_handle_api_etc_reconciliation_reopen`
  - `_handle_api_etc_reconciliation_refresh_matches`
- Kept upload/parser-heavy callbacks intentionally unchanged:
  - `_handle_api_etc_reconciliation_upload`
  - `_handle_api_etc_reconciliation_supplement_for_card_upload`
  - `_handle_api_etc_reconciliation_ticket_root_texts`
- Extended the reconciliation route-owner Guard so the moved callbacks cannot return to `server.py`, while preserving the explicit upload/parser callback stop gate.

## Boundary Result

`server.py` no longer owns simple ETC reconciliation task mutation HTTP mapping. It still owns upload/parser-heavy callback bodies pending a separate boundary because those flows include multipart parsing, object storage, parser selection, ticket-root source-mode validation and wrong-slot detection.

`EtcReconciliationTaskApiRoutes` still receives explicit task service, payload, expected-version and error-response ports, not `Application`.

## Tests

- Updated `test_etc_reconciliation_task_routes_delegate_to_route_owner`.
- Reused targeted API regressions for confirm, source-file delete, stale confirmability and refresh-matches behavior.

## Verification

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_reconciliation.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_reconciliation_confirm_route_accepts_selected_credit_card_item_ids tests.test_etc_backend.EtcApiTests.test_delete_reconciliation_source_file_route_removes_file_parse_result_and_items tests.test_etc_backend.EtcApiTests.test_delete_reconciliation_source_file_route_requires_version_and_mutable_status tests.test_etc_backend.EtcApiTests.test_reconciliation_task_payload_is_not_confirmable_with_stale_included_etc_resolution -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_refresh_reconciliation_matches_route_recalculates_and_returns_task tests.test_etc_backend.EtcApiTests.test_refresh_reconciliation_matches_route_returns_404_for_unknown_task -v`

Note: two earlier refresh-matches test invocations failed because the test names were stale. The exact `rg`-discovered test names passed.

## Next Boundary

`server-py:etc-reconciliation-upload-parser-callback-audit`

Reason: the remaining reconciliation callbacks in `server.py` are upload/parser-heavy flows. They need a dedicated audit before choosing route-owner migration, upload application-service extraction, or smaller parser/source-mode sub-boundaries.
