# server-py Workbench confirm-link submit route owner extraction

Date: 2026-06-24
Boundary: `server-py:workbench-confirm-link-submit-route-owner-extraction`
Status: `implementation-closed`

## Goal

Move `/api/workbench/actions/confirm-link` live facade delegation out of
`Application` and behind `WorkbenchActionApiRoutes`, while preserving the
existing app-level JSON parsing, freshness guard, auth context, request timing
and response mapping.

## Changes

- Added `WorkbenchActionApiRoutes.confirm_link(...)`.
- Moved `WorkbenchWriteFacade.confirm_link(...)` invocation into the route owner.
- Kept `Application._handle_api_workbench_confirm_link(...)` responsible for
  JSON body parsing, Workbench write freshness guard, auth context resolution
  and request timing envelope.
- Kept `Application._handle_live_workbench_confirm_link(...)` responsible for
  `_workbench_write_response(...)` serialization.
- Added a static guard proving confirm-link submit facade delegation is
  route-owned while the app wrapper still preserves freshness/auth/request-id
  forwarding and response mapping.

## Preserved Contract

- Invalid JSON is still handled by `Application._load_json_body(...)`.
- Freshness guard still runs before the facade call.
- Auth context still resolves through `Application._workbench_write_auth_context(...)`.
- Request timing behavior is unchanged.
- Delegate remains `WorkbenchWriteFacade.confirm_link(...)`.
- `request_id`, `actor_id` and `tenant_id` are forwarded unchanged.
- Response mapping still goes through `_workbench_write_response(...)`.
- No idempotency, UoW, relation write, operation projection, operation barrier,
  read model refresh, frontend API or legacy route behavior changed.

## Non-Goals

- Did not move cancel, withdraw, cash special, bank exception, OA-bank exception,
  personal advance repayment, cancel exception, ignore, unignore, exception
  preview/apply or confirm-link preview routes.
- Did not change legacy `/workbench/actions/*`.
- Did not implement Go, Go Fiber or Go Worker.
- Did not perform production writes, deploy, restart services, requeue jobs,
  mark scopes done, mutate readiness or run repair tools with `--apply`.

## Test Category Decision

Covered:

- API contract tests: targeted Workbench V2 confirm-link submit tests preserve
  mismatch note handling, phased timing logs and persistence failure rollback.
- Service-layer tests: Workbench write characterization tests preserve UoW
  transaction usage and idempotent replay without duplicate outbox events.
- Existing feature regression tests: static guards preserve route-owner
  ownership and Go admission blocking.

Not applicable:

- Business core unit tests: no amount rule, grouping rule, state transition or
  relation rule changed.
- Read model/cache/background job tests: no dirty scope, worker, cache,
  operation barrier or freshness semantics changed.
- Frontend component/interaction tests: no frontend contract changed.
- End-to-end business-flow tests: targeted backend API/characterization coverage
  is sufficient for this ownership-only extraction.

## State Machine Impact

- `MODULE-QUEUE.md` row 198 should move from `pending` to
  `implementation-closed`.
- Add row 199 as `server-py:workbench-mark-exception-route-owner-extraction`
  with `pending`.
- `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and
  `prompts/04-master-goal-controller.md` should point to row 199.
- Global state definitions in `03-REFACTOR-STATE-MACHINE.md` are unchanged.
- Module state-machine definitions are unchanged; module implementation notes
  record the route-owner ownership change.

## Verification

Target commands:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_and_submit_require_note_for_amount_mismatch tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_emits_phased_timing_logs tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_returns_503_and_rolls_back_when_pair_relation_persist_fails tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_confirm_link_uses_uow_transaction_when_available tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_confirm_link_uow_replays_same_idempotency_key_without_duplicate_outbox tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_confirm_link_submit_delegation_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```
