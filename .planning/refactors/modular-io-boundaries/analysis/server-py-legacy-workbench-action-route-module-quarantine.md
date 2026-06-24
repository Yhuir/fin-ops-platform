# Legacy Workbench Action Route Module Quarantine

**Date:** 2026-06-24
**Boundary:** `server-py:legacy-workbench-action-route-module-quarantine`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Isolate old `/workbench/actions/*` HTTP/payload mapping behind an explicit legacy Workbench action route owner while preserving behavior. Keep modern `/api/workbench/actions/*` facade-backed and unchanged.

## Implementation

- Added `backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py`.
- Introduced `LegacyWorkbenchActionRoutes` as the compat-only route owner for:
  - `POST /workbench/actions/confirm`
  - `POST /workbench/actions/difference`
  - `POST /workbench/actions/exception`
  - `POST /workbench/actions/offline`
  - `POST /workbench/actions/offset`
- Moved the old payload validation, `ManualReconciliationService` calls and `LedgerReminderService.sync_from_case(...)` behavior into `LegacyWorkbenchActionRoutes`.
- Registered `Application._legacy_workbench_action_routes`.
- Replaced old route dispatch calls with `Application._handle_legacy_workbench_action(action, body)`, which now only parses JSON, delegates to the legacy route owner and maps the result through `_json_response(...)`.
- Removed `Application._handle_workbench_confirm(...)`, `_handle_workbench_difference(...)`, `_handle_workbench_exception(...)`, `_handle_workbench_offline(...)`, and `_handle_workbench_offset(...)`.
- Added a static guard proving:
  - `server.py` no longer owns the five legacy handlers,
  - legacy route mapping delegates through `LegacyWorkbenchActionRoutes`,
  - the legacy route owner keeps old reconciliation/ledger behavior,
  - the legacy owner does not use `WorkbenchWriteFacade`, `WorkbenchRelationCommandService`, `ReadModelRefreshGateway`, or direct job queue SQL,
  - modern `/api/workbench/actions/*` wrappers still delegate to `WorkbenchWriteFacade`.

## Boundary Decision

This is a quarantine implementation, not a deletion. The old endpoints still exist because `tests/test_ledger_api.py` validates ledger/reminder behavior through `/workbench/actions/confirm` and `/workbench/actions/exception`.

The change reduces old-code pollution by moving old action logic out of the main `Application` class and making the legacy boundary explicit. It does not migrate legacy ledger semantics into modern Workbench relation command service.

## Next Selected Boundary

`server-py:legacy-workbench-exception-helper-dead-code-audit`

Reason:

- `_handle_legacy_workbench_exception_via_application(...)` still remains in `server.py`.
- The previous audit found no current route dispatch caller.
- It overlaps modern `/api/workbench/exception/preview` and `/api/workbench/exception/apply` behavior.
- Before removal, it needs a focused caller/test/API evidence audit to classify it as dead removable code or compat-only retained helper.

## State Machine Impact

- `server-py:legacy-workbench-action-route-module-quarantine` transitions to `implementation-closed`.
- Insert `server-py:legacy-workbench-exception-helper-dead-code-audit` as the next pending boundary.
- Go/Fiber/Go Worker admission remains blocked.
- Global state-machine definitions are unchanged; this is an implementation slice covered by the existing `implementation-closed` label.
- No module state-machine definitions changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No reconciliation or ledger business rule changed. |
| 2. Service-layer tests | Not applicable | No service behavior changed; behavior moved behind route owner. |
| 3. API contract tests | Applicable | Legacy endpoint behavior and health entrypoints are covered by `tests.test_ledger_api` and `tests.test_app.AppTests.test_health_endpoint_reports_current_and_future_capabilities`. |
| 4. Read model/cache/background job tests | Not applicable | No read model, queue, cache or worker behavior changed. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this narrow slice | Existing backend ledger flow tests cover the affected legacy API behavior. |
| 7. Existing feature regression tests | Applicable | Added platform static guard for legacy route quarantine and modern facade preservation. |

## Verification

Executed:

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_app.AppTests.test_health_endpoint_reports_current_and_future_capabilities \
  tests.test_ledger_api \
  -v

PYTHONPATH=backend/src python3 -m unittest \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded \
  -v

python3 -m py_compile \
  backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py \
  backend/src/fin_ops_platform/app/server.py \
  tests/test_platform_runtime_boundary_guards.py
```

Remaining before commit:

```bash
PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- Legacy `/workbench/actions/*` still exists and remains compat-only. It is isolated but not deleted.
- A future ledger replacement or explicit product retirement decision is needed before removing these endpoints.
- `_handle_legacy_workbench_exception_via_application(...)` still remains in `server.py` and needs the selected follow-up audit.
