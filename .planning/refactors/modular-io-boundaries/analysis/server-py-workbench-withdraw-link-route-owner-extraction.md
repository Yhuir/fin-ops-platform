# server-py Workbench withdraw-link route owner extraction

Date: 2026-06-24
Boundary: `server-py:workbench-withdraw-link-route-owner-extraction`
Status: `implementation-closed`

## Goal

Move `/api/workbench/actions/withdraw-link` facade delegation out of
`Application` and behind `WorkbenchActionApiRoutes`, while preserving the
existing app-level JSON parsing, freshness guard, auth context and response
mapping.

## Changes

- Added `WorkbenchActionApiRoutes.withdraw_link(...)`.
- Moved `WorkbenchWriteFacade.withdraw_link(...)` invocation into the route owner.
- Kept `Application._handle_api_workbench_withdraw_link(...)` responsible for
  JSON body parsing, Workbench write freshness guard, auth context resolution
  and response mapping.
- Kept `Application._handle_live_workbench_withdraw_link(...)` as a thin helper
  that delegates through the same route owner and serializes
  `_workbench_write_response(...)`.
- Added a static guard proving withdraw-link facade delegation is route-owned
  while the app wrapper still preserves freshness/auth/request-id forwarding and
  response mapping.
- Narrowed the legacy Workbench action quarantine guard so it no longer expects
  already extracted modern action route-owner helpers to call the write facade
  directly.

## Preserved Contract

- Invalid JSON is still handled by `Application._load_json_body(...)`.
- Freshness guard still runs before the facade call.
- Auth context still resolves through `Application._workbench_write_auth_context(...)`.
- Delegate remains `WorkbenchWriteFacade.withdraw_link(...)`.
- `request_id`, `actor_id` and `tenant_id` are forwarded unchanged from the API
  wrapper to the facade.
- Response mapping still goes through `_workbench_write_response(...)`.
- No idempotency, UoW, relation write, operation projection, operation barrier,
  read model refresh, frontend API or legacy route behavior changed.

## Non-Goals

- Did not move cash special, bank exception, OA-bank exception, personal advance
  repayment, cancel exception, ignore, unignore, exception preview/apply,
  confirm-link preview/submit, mark-exception or cancel-link routes.
- Did not change legacy `/workbench/actions/*`.
- Did not implement Go, Go Fiber or Go Worker.
- Did not perform production writes, deploy, restart services, requeue jobs,
  mark scopes done, mutate readiness or run repair tools with `--apply`.

## Test Category Decision

Covered:

- API contract tests: targeted Workbench V2 withdraw-link tests preserve snapshot
  restore and no-history fallback behavior.
- Service-layer tests: Workbench write characterization tests preserve UoW,
  affected scope and scheduling failure rollback behavior.
- Existing feature regression tests: static guards preserve route-owner
  ownership, legacy quarantine and Go admission blocking.

Not applicable:

- Business core unit tests: no amount rule, grouping rule, state transition or
  relation rule changed.
- Read model/cache/background job tests: no dirty scope, worker, cache,
  operation barrier or freshness semantics changed.
- Frontend component/interaction tests: no frontend contract changed.
- End-to-end business-flow tests: targeted backend API/characterization coverage
  is sufficient for this ownership-only extraction.

## State Machine Impact

- `MODULE-QUEUE.md` row 201 moves from `pending` to `implementation-closed`.
- Add row 202 as `server-py:workbench-cash-special-route-owner-extraction`
  with `pending`.
- `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and
  `prompts/04-master-goal-controller.md` should point to row 202.
- Global state definitions in `03-REFACTOR-STATE-MACHINE.md` are unchanged.
- Module state-machine definitions are unchanged; module implementation notes
  record the route-owner ownership change.

## Verification

Target commands:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_withdraw_link_uses_uow_transaction_when_available tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_withdraw_link_invalidates_only_affected_scopes_without_global_all tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_withdraw_link_read_model_scheduling_failure_rolls_back_relation_withdraw tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_withdraw_link_restores_previous_relation_snapshot tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_withdraw_link_without_history_falls_back_to_cancelling_active_relation tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_withdraw_link_delegation_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```
