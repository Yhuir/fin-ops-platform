# server-py Workbench cash special route owner extraction

Date: 2026-06-24
Boundary: `server-py:workbench-cash-special-route-owner-extraction`
Status: `implementation-closed`

## Goal

Move cash special action facade delegation out of `Application` and behind
`WorkbenchActionApiRoutes`, while preserving the existing app-level JSON
parsing, freshness guard, request-id forwarding and response mapping.

## Changes

- Added `WorkbenchActionApiRoutes.confirm_cash_pass_through(...)`.
- Added `WorkbenchActionApiRoutes.confirm_cash_ticket_purchase(...)`.
- Added `WorkbenchActionApiRoutes.cancel_cash_special(...)`.
- Moved `WorkbenchWriteFacade.confirm_cash_pass_through(...)`,
  `confirm_cash_ticket_purchase(...)`, and `cancel_cash_special(...)`
  invocation into the route owner.
- Kept the three `Application._handle_api_workbench_*cash*` wrappers
  responsible for JSON body parsing, Workbench write freshness guard and
  `_workbench_write_response(...)` serialization.
- Added a static guard proving cash special facade delegation is route-owned
  while app wrappers still preserve JSON/freshness/request-id/response mapping.

## Preserved Contract

- Invalid JSON is still handled by `Application._load_json_body(...)`.
- Freshness guard still runs before the facade call.
- Delegates remain the existing `WorkbenchWriteFacade` cash special methods.
- `request_id` is forwarded unchanged.
- Response mapping still goes through `_workbench_write_response(...)`.
- No idempotency, stale expected-relation conflict, special metadata mutation,
  relation write, operation projection, operation barrier, read model refresh,
  frontend API or legacy route behavior changed.

## Non-Goals

- Did not move bank exception, OA-bank exception, personal advance repayment,
  cancel exception, ignore, unignore, exception preview/apply, confirm-link
  preview/submit, mark-exception, cancel-link or withdraw-link routes.
- Did not change legacy `/workbench/actions/*`.
- Did not implement Go, Go Fiber or Go Worker.
- Did not perform production writes, deploy, restart services, requeue jobs,
  mark scopes done, mutate readiness or run repair tools with `--apply`.

## Test Category Decision

Covered:

- Service-layer tests: Workbench write characterization tests preserve duplicate
  cash special replay, stale current-relation behavior, stale expected-relation
  rejection and scheduling failure behavior.
- Existing feature regression tests: static guards preserve route-owner
  ownership, legacy quarantine and Go admission blocking.

Not applicable:

- Business core unit tests: no amount rule, metadata rule, state transition or
  relation rule changed.
- API contract tests: existing characterization tests exercise the API boundary
  and response shapes; no HTTP contract changed.
- Read model/cache/background job tests: no dirty scope, worker, cache,
  operation barrier or freshness semantics changed.
- Frontend component/interaction tests: no frontend contract changed.
- End-to-end business-flow tests: targeted backend characterization coverage is
  sufficient for this ownership-only extraction.

## State Machine Impact

- `MODULE-QUEUE.md` row 202 moves from `pending` to `implementation-closed`.
- Add row 203 as `server-py:workbench-update-bank-exception-route-owner-extraction`
  with `pending`.
- `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and
  `prompts/04-master-goal-controller.md` should point to row 203.
- Global state definitions in `03-REFACTOR-STATE-MACHINE.md` are unchanged.
- Module state-machine definitions are unchanged; module implementation notes
  record the route-owner ownership change.

## Verification

Target commands:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_duplicate_cash_special_updates_and_clears_are_replayed_current_behavior tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_stale_cash_special_updates_first_active_relation_for_rows_current_behavior tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cash_special_with_stale_expected_relation_rejects_all_entrypoints tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_cash_special_scheduling_failure_propagates_after_metadata_mutation tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_cash_special_delegation_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```
