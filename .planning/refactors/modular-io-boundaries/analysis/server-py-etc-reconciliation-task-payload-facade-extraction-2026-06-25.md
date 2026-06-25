# server-py:etc-reconciliation-task-payload-facade-extraction

Date: 2026-06-25
Status: local-implementation-closed

## Goal

Move ETC reconciliation task payload/read-shaping ownership out of `Application` into an explicit facade while preserving route response shape and route-owner behavior.

## Files Changed

- `backend/src/fin_ops_platform/services/etc_reconciliation_task_payload_facade.py`
- `backend/src/fin_ops_platform/app/server.py`
- `tests/test_etc_reconciliation_service.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/etc-tickets/implementation-notes.md`

## Implementation

Added `EtcReconciliationTaskPayloadFacade` with explicit dependencies:

- `etc_import_batch_by_id: Callable[[str], object | None]`
- `serialize_value: Callable[[object], Any]`

The facade now owns:

- task payload;
- unavailable task payload;
- import blockers;
- imported invoice summary;
- source-file payloads;
- parse issue payloads;
- `canConfirm`;
- linked ETC/supplement evidence helper calculations.

`Application._etc_reconciliation_routes(...)` now builds the facade through `_etc_reconciliation_task_payload_facade()` and injects:

- `task_payload=payload_facade.task_payload`
- `unavailable_task_payload=payload_facade.unavailable_task_payload`

The old payload helper implementations were removed from `server.py`. `server.py` now only assembles the facade from existing dependencies and still owns generic HTTP JSON serialization.

## Tests Added Or Changed

- Added direct facade tests:
  - created task payload and import blockers;
  - imported invoice summary through explicit import-batch lookup;
  - stale included-ETC resolution remains not confirmable.
- Updated one existing backend regression to call the facade factory instead of the removed app helper.
- Extended the route-owner static Guard to require explicit payload facade wiring and forbid helper implementations from returning to `server.py`.

## Verification

Passed:

- `PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_reconciliation_task_payload_facade.py backend/src/fin_ops_platform/app/server.py tests/test_etc_reconciliation_service.py tests/test_platform_runtime_boundary_guards.py tests/test_etc_backend.py`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_task_payload_facade_builds_created_payload_and_import_blockers tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_task_payload_facade_uses_import_batch_lookup_for_imported_summary tests.test_etc_reconciliation_service.EtcReconciliationServiceTests.test_task_payload_facade_blocks_stale_included_etc_resolution -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner -v`
- `PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_created_reconciliation_task_payload_is_fresh_and_includes_source_files tests.test_etc_backend.EtcApiTests.test_ready_for_import_lists_unavailable_unconfirmed_tasks_with_blocker tests.test_etc_backend.EtcApiTests.test_reconciliation_task_payload_includes_source_file_context_for_parse_issues tests.test_etc_backend.EtcApiTests.test_reconciliation_task_payload_is_not_confirmable_with_stale_included_etc_resolution tests.test_etc_backend.EtcApiTests.test_task_aware_etc_import_does_not_create_independent_batch_list_item tests.test_etc_backend.EtcApiTests.test_remove_reconciliation_task_imported_invoices_allows_reimport -v`

## Seven Test Category Decision

- Business core unit tests: covered through `canConfirm` and blocker/summary facade tests.
- Service-layer tests: covered through direct facade tests.
- API contract tests: covered through targeted ETC API response-shape regressions.
- Read model/cache/background job tests: not applicable; this slice changes route payload composition only and does not touch read model refresh, cache or workers.
- Frontend component and interaction tests: not applicable; response shape is preserved and no frontend behavior changed.
- End-to-end business-flow integration tests: partially covered by import/remove imported invoice API regressions; broader E2E is not required for this narrow backend facade extraction.
- Existing feature regression tests: covered by existing ETC payload/import/remove regressions and static route-owner Guard.

## Docs Impact

Updated ETC tickets implementation notes and modular IO autonomous state files. Product/API long-term docs are unchanged because response shape and business behavior are unchanged.

## Remaining Risk

ETC reconciliation route-owner local closure still needs a post-extraction audit to confirm no residual `Application` ownership remains for this route surface. Production browser/admin/write validation remains final validation only and was not run.

## Next Boundary

`server-py:etc-reconciliation-post-payload-facade-local-closure-audit`
