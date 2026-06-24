# server-py Workbench mark-exception route owner extraction

Date: 2026-06-24
Boundary: `server-py:workbench-mark-exception-route-owner-extraction`
Status: `implementation-closed`

## Goal

Move `/api/workbench/actions/mark-exception` facade delegation out of
`Application` and behind `WorkbenchActionApiRoutes`, while preserving the
existing app-level JSON parsing, freshness guard and response mapping.

## Changes

- Added `WorkbenchActionApiRoutes.mark_exception(...)`.
- Moved `WorkbenchWriteFacade.mark_exception(...)` invocation into the route owner.
- Kept `Application._handle_api_workbench_mark_exception(...)` responsible for
  JSON body parsing and the Workbench write freshness guard.
- Kept `Application._handle_live_workbench_mark_exception(...)` responsible for
  `_workbench_write_response(...)` serialization.
- Added a static guard proving mark-exception facade delegation is route-owned
  while the app wrapper still preserves freshness gating and response mapping.

## Preserved Contract

- Invalid JSON is still handled by `Application._load_json_body(...)`.
- Freshness guard still runs before the facade call.
- Delegate remains `WorkbenchWriteFacade.mark_exception(...)`.
- Response mapping still goes through `_workbench_write_response(...)`.
- No idempotency, relation write, operation projection, operation barrier,
  read model refresh, frontend API or legacy route behavior changed.

## Non-Goals

- Did not move cancel, withdraw, cash special, bank exception, OA-bank exception,
  personal advance repayment, cancel exception, ignore, unignore, exception
  preview/apply or confirm-link preview/submit routes.
- Did not change legacy `/workbench/actions/*`.
- Did not implement Go, Go Fiber or Go Worker.
- Did not perform production writes, deploy, restart services, requeue jobs,
  mark scopes done, mutate readiness or run repair tools with `--apply`.

## Test Category Decision

Covered:

- API contract tests: targeted Workbench V2 mark-exception tests preserve changed
  scope invalidation and failure response behavior.
- Service-layer tests: Workbench write characterization tests preserve duplicate
  mark-exception idempotent replay behavior.
- Existing feature regression tests: static guards preserve route-owner ownership
  and Go admission blocking.

Not applicable:

- Business core unit tests: no amount rule, grouping rule, state transition or
  relation rule changed.
- Read model/cache/background job tests: no dirty scope, worker, cache,
  operation barrier or freshness semantics changed.
- Frontend component/interaction tests: no frontend contract changed.
- End-to-end business-flow tests: targeted backend API/characterization coverage
  is sufficient for this ownership-only extraction.

## State Machine Impact

- `MODULE-QUEUE.md` row 199 moves from `pending` to `implementation-closed`.
- Add row 200 as `server-py:workbench-cancel-link-route-owner-extraction`
  with `pending`.
- `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and
  `prompts/04-master-goal-controller.md` should point to row 200.
- Global state definitions in `03-REFACTOR-STATE-MACHINE.md` are unchanged.
- Module state-machine definitions are unchanged; module implementation notes
  record the route-owner ownership change.

## Verification

Target commands:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_duplicate_mark_exception_reuses_existing_case_and_replays_success tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_mark_exception_invalidates_only_changed_scopes_and_rebuilds_in_background tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_mark_exception_returns_503_and_keeps_workbench_loadable_when_override_persist_fails tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_mark_exception_delegation_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```
