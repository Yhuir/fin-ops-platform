# server.py ETC reconciliation task route owner facade extraction

- Date: 2026-06-25
- Boundary: `server-py:etc-reconciliation-task-route-owner-facade-extraction`
- Status: `local-implementation-closed`
- Module closure: `implementation-gap-open`
- Production: not used

## Result

Implemented the first local ETC reconciliation route-owner extraction slice.

Runtime changes:

- Added `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py::EtcReconciliationTaskApiRoutes`.
- Moved `/api/etc/reconciliation-tasks`, `/api/etc/reconciliation-tasks/ready-for-import`, task detail, and task subroute dispatch out of `Application`.
- Updated `Application._handle_request_untracked(...)` to delegate `/api/etc/reconciliation-tasks*` to `self._etc_reconciliation_routes().route(...)`.
- Added `Application._etc_reconciliation_routes(...)` as dependency assembly only.
- Deleted the unused app-owned root/list/create/detail/subroute dispatch helpers:
  - `_handle_api_etc_reconciliation_tasks`
  - `_handle_api_etc_reconciliation_ready_for_import`
  - `_handle_api_etc_reconciliation_task_create`
  - `_route_api_etc_reconciliation_task`
- Kept complex upload/delete/import side-effect handlers in `Application` as explicit callbacks for this slice.

## Boundary Decision

The new route owner owns URL subrouting and lightweight HTTP parsing/response mapping for reconciliation task root/detail/ready/create routes. It receives explicit dependencies:

- task service;
- JSON response and JSON body loader callbacks;
- task payload serializers;
- upload/source/delete/task mutation callbacks.

It does not receive the whole `Application`.

This slice intentionally did not move:

- `/api/etc/import/*`;
- legacy `/api/etc/batches*`;
- imported-invoice delete internals;
- task-delete business-batch/source cleanup internals;
- Workbench relation summary cancellation or derived lifecycle refresh.

Those remain separate local implementation boundaries because they mix route ownership with service-side side effects and read-model fan-out.

## Tests Added Or Changed

Changed:

- `tests/test_platform_runtime_boundary_guards.py`
  - Added `test_etc_reconciliation_task_routes_delegate_to_route_owner`.

Existing tests rerun:

- Targeted ETC reconciliation route API tests in `tests/test_etc_backend.py`.
- Existing ETC route boundary guards in `tests/test_platform_runtime_boundary_guards.py`.

## Seven Test Categories

1. Business core unit tests: covered by targeted ETC route tests that preserve task version/status validation and confirm/refresh behavior.
2. Service-layer tests: not directly changed; complex side-effect handlers remain delegated to existing services/helpers.
3. API contract tests: covered by targeted `tests.test_etc_backend.EtcApiTests` route tests for create/list/ready/detail, confirm, refresh, source-file delete, and task delete.
4. Read model/cache/background job tests: not directly applicable; this slice did not move imported-invoice delete internals, background jobs, read-model enqueue, or derived lifecycle refresh.
5. Frontend component and interaction tests: not directly applicable; backend API shape and page behavior are unchanged.
6. End-to-end business-flow integration tests: partially covered by targeted backend integration-style ETC route tests; browser flow unchanged and not rerun.
7. Existing feature regression tests: covered by ETC backend route regressions plus platform runtime boundary guards.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_etc_reconciliation.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_reconciliation_task_routes_delegate_to_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_business_batch_routes_do_not_keep_removed_legacy_handlers tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_summary_relation_delete_uses_workbench_relation_command_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_reconciliation_task_routes_create_list_ready_and_get_without_route_swallowing tests.test_etc_backend.EtcApiTests.test_ready_for_import_lists_unavailable_unconfirmed_tasks_with_blocker tests.test_etc_backend.EtcApiTests.test_reconciliation_confirm_route_accepts_selected_credit_card_item_ids tests.test_etc_backend.EtcApiTests.test_refresh_reconciliation_matches_route_recalculates_and_returns_task tests.test_etc_backend.EtcApiTests.test_refresh_reconciliation_matches_route_returns_404_for_unknown_task tests.test_etc_backend.EtcApiTests.test_delete_reconciliation_source_file_route_removes_file_parse_result_and_items tests.test_etc_backend.EtcApiTests.test_delete_reconciliation_task_route_requires_mutable_status_and_version -v
```

Initial failed checks:

- A targeted unittest command used a stale test name; the correct test was rerun and passed.
- The first route owner import used the wrong `SourceFileKind` module; fixed to `fin_ops_platform.services.etc_reconciliation_models`.
- The new static guard initially inspected `handle_request` instead of `_handle_request_untracked`; fixed and rerun.

## Docs Impact

Updated `docs/modules/etc-tickets/implementation-notes.md` because internal route ownership changed for ETC reconciliation task endpoints.

Long-term product/API docs are unchanged: API paths, payload shape, state machine, permissions, and business semantics did not change.

## Remaining Risk

Local implementation gaps remain:

- task delete and imported-invoice delete still coordinate business-batch cleanup, Workbench relation preflight/cancellation, derived lifecycle refresh, and state persistence from `Application` callbacks;
- `/api/etc/import/*` still lives in `Application`;
- legacy `/api/etc/batches*` still lives in `Application`;
- production browser/admin/write evidence remains final validation only.

## Next Boundary

`server-py:etc-reconciliation-task-delete-side-effect-service-audit`

Audit task delete/imported-invoice delete callbacks and decide whether the next safe slice should extract a service boundary, a callback port, or a compat-only quarantine before moving `/api/etc/import/*`.
