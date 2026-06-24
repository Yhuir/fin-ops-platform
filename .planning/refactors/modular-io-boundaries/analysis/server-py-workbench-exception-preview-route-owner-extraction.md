# server-py Workbench exception preview route owner extraction

Date: 2026-06-24
Boundary: `server-py:workbench-exception-preview-route-owner-extraction`
Status: `implementation-closed`

## Goal

Move the modern `/api/workbench/exception/preview` payload/error mapping out of
`Application` and behind an explicit route owner while preserving API behavior.

This is the first modern Workbench action route-owner extraction after the
modern action route-owner audit. It intentionally does not move exception apply
or the larger confirm/cancel/withdraw/cash/ignore action group.

## Changes

- Added `backend/src/fin_ops_platform/app/routes_workbench_actions.py`.
- Added `WorkbenchActionApiRoutes.exception_preview(...)`.
- Wired `Application` to instantiate `WorkbenchActionApiRoutes` with
  `WorkbenchExceptionApplicationService`.
- Changed `_handle_api_workbench_exception_preview(...)` so `Application`
  still handles HTTP dispatch and JSON body parsing, but delegates preview
  status/payload mapping to `WorkbenchActionApiRoutes`.
- Extended the static route owner inventory guard so the new route module must
  stay registered, imported and delegated from `server.py`.
- Added a guard proving exception preview mapping is owned by
  `WorkbenchActionApiRoutes`, not the app wrapper.

## Preserved Contract

- Invalid JSON is still handled by `Application._load_json_body(...)`.
- `WorkbenchExceptionApplicationService.preview(payload)` remains the business
  delegate.
- `KeyError` still maps to `404` with `error=workbench_row_not_found`.
- `TypeError` and `ValueError` still map to `400` with
  `error=invalid_workbench_exception_preview_request`.
- Success still maps to `200` with the preview payload.
- No freshness guard, auth context, request id, request timing, relation write,
  operation barrier, read model refresh or frontend behavior changed.

## Non-Goals

- Did not move `/api/workbench/exception/apply`.
- Did not move confirm/cancel/withdraw, cash special, bank exception,
  OA-bank exception, personal advance repayment, cancel exception, ignore or
  unignore routes.
- Did not change legacy `/workbench/actions/*`.
- Did not implement Go, Go Fiber or Go Worker.
- Did not perform production writes, deploy, restart services, requeue jobs,
  mark scopes done, mutate readiness or run repair tools with `--apply`.

## Test Category Decision

Covered:

- API contract tests: targeted Workbench V2 exception preview test preserves
  route status/payload behavior.
- Service-layer tests: static route owner guard verifies route/service ownership
  and prevents the mapping from returning to `Application`.
- Existing feature regression tests: route owner inventory and Go admission
  guard keep server-py modularization and Go blocking state aligned.

Not applicable:

- Business core unit tests: no business rule or scenario classifier changed.
- Read model/cache/background job tests: no freshness, dirty scope, outbox,
  worker or cache behavior changed.
- Frontend component/interaction tests: no frontend contract changed.
- End-to-end business-flow tests: this slice only moved server-side ownership
  for an already covered API mapping.

## State Machine Impact

- `MODULE-QUEUE.md` row 195 should move from `pending` to
  `implementation-closed`.
- Add row 196 as `server-py:workbench-exception-apply-route-owner-extraction`
  with `pending`.
- `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and
  `prompts/04-master-goal-controller.md` should point to row 196.
- Global state definitions in `03-REFACTOR-STATE-MACHINE.md` are unchanged.
- Module state-machine definitions are unchanged; module implementation notes
  record the route-owner ownership change.

## Verification

Target commands:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_exception_preview_api_returns_backend_scenario_for_oa_bank_missing_invoice tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_exception_preview_mapping_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```
