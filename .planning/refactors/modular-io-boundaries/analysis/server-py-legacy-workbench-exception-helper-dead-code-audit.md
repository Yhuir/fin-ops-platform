# Legacy Workbench Exception Helper Dead-Code Audit

**Date:** 2026-06-24
**Boundary:** `server-py:legacy-workbench-exception-helper-dead-code-audit`
**Slice status:** `implementation-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit `_handle_legacy_workbench_exception_via_application(...)` after legacy Workbench action route quarantine and remove it if caller evidence proves it is dead.

## Evidence

Literal search across backend, tests, frontend and e2e found no caller for `_handle_legacy_workbench_exception_via_application(...)`.

Current exception API evidence:

- Backend route dispatch uses:
  - `POST /api/workbench/exception/preview` -> `_handle_api_workbench_exception_preview(...)`
  - `POST /api/workbench/exception/apply` -> `_handle_api_workbench_exception_apply(...)`
- Frontend and Browser tests call `/api/workbench/exception/preview` and `/api/workbench/exception/apply`.
- Modern exception application behavior is covered through `WorkbenchExceptionApplicationService`, `WorkbenchWriteFacade.apply_exception(...)`, and Workbench v2/selection/exception tests.
- The helper only called `_workbench_exception_application_service.preview(...)` plus `_apply_workbench_exception_application(...)` internally, but no route or test invoked the helper itself.

## Implementation

- Removed `Application._handle_legacy_workbench_exception_via_application(...)`.
- Removed the now-unused `WorkbenchExceptionApplicationConflict` import from `server.py`.
- Extended the legacy Workbench action quarantine guard to prevent `_handle_legacy_workbench_exception_via_application(...)` from returning.

## Boundary Decision

The helper was removable dead code. It did not own a public route, frontend API, test fixture or modern Workbench exception contract.

This does not change:

- `/api/workbench/exception/preview`
- `/api/workbench/exception/apply`
- old `/workbench/actions/*` legacy ledger endpoints
- Workbench relation command behavior
- read model refresh behavior

## Next Selected Boundary

`server-py:modern-workbench-action-route-owner-audit`

Reason:

- Legacy action routes are now quarantined.
- The no-caller legacy exception helper is removed.
- Modern `/api/workbench/actions/*` and `/api/workbench/exception/*` wrappers still live in `server.py`.
- They already delegate to `WorkbenchWriteFacade` or `WorkbenchExceptionApplicationService`, so the next safe step is an audit that classifies which modern Workbench action wrappers can move behind an explicit route owner without touching business semantics.

## State Machine Impact

- `server-py:legacy-workbench-exception-helper-dead-code-audit` transitions to `implementation-closed`.
- Insert `server-py:modern-workbench-action-route-owner-audit` as the next pending boundary.
- Go/Fiber/Go Worker admission remains blocked.
- Global state-machine definitions are unchanged; this slice is covered by existing `implementation-closed` semantics.
- No module state-machine definitions changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | Removed dead route helper; no business rule changed. |
| 2. Service-layer tests | Not applicable | No service behavior changed. |
| 3. API contract tests | Applicable by regression | Modern exception API routes should still pass existing Workbench v2/exception route tests. |
| 4. Read model/cache/background job tests | Not applicable | No read model, queue, cache or worker behavior changed. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable for this narrow deletion | No public route behavior changed. |
| 7. Existing feature regression tests | Applicable | Static guard prevents the dead helper from returning and keeps Go blocked. |

## Verification

Targeted verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded \
  -v

PYTHONPATH=backend/src python3 -m unittest \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_exception_preview_api_returns_backend_scenario_for_oa_bank_missing_invoice \
  tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_exception_apply_api_creates_closed_case_and_pair_relation \
  -v

bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- Modern Workbench action wrappers still live in `server.py`; the selected next audit should decide the safe route-owner extraction sequence.
- Legacy `/workbench/actions/*` endpoints remain compat-only through `LegacyWorkbenchActionRoutes`; deletion still needs a ledger/follow-up replacement or explicit retired decision.
