# server-py Workbench exception apply route owner extraction

Date: 2026-06-24
Boundary: `server-py:workbench-exception-apply-route-owner-extraction`
Status: `implementation-closed`

## Goal

Move `/api/workbench/exception/apply` facade delegation and actor/request-id
mapping out of `Application` and behind `WorkbenchActionApiRoutes`, while
preserving the existing freshness guard and response mapping.

## Changes

- Extended `WorkbenchActionApiRoutes` with a `write_facade_provider`.
- Added `WorkbenchActionApiRoutes.exception_apply(...)`.
- Moved `WorkbenchWriteFacade.apply_exception(...)` invocation, actor fallback
  and `action_name="exception_apply"` mapping into the route owner.
- Kept `Application._handle_api_workbench_exception_apply(...)` responsible for
  JSON body parsing, Workbench write freshness guard and
  `_workbench_write_response(...)`.
- Added a static guard proving exception apply delegation/actor mapping is
  route-owned and the app wrapper still preserves freshness and write-response
  mapping.

## Preserved Contract

- Invalid JSON is still handled by `Application._load_json_body(...)`.
- Freshness guard still runs before the facade call.
- Delegate remains `WorkbenchWriteFacade.apply_exception(...)`.
- Actor remains `payload["actor"] || payload["confirmed_by"] || "system"`.
- `request_id` is forwarded unchanged.
- `action_name` remains `exception_apply`.
- Response mapping still goes through `_workbench_write_response(...)`.
- No relation write semantics, idempotency, operation barrier, read model refresh,
  frontend API or legacy route behavior changed.

## Non-Goals

- Did not move confirm/cancel/withdraw, cash special, bank exception,
  OA-bank exception, personal advance repayment, cancel exception, ignore or
  unignore routes.
- Did not change legacy `/workbench/actions/*`.
- Did not implement Go, Go Fiber or Go Worker.
- Did not perform production writes, deploy, restart services, requeue jobs,
  mark scopes done, mutate readiness or run repair tools with `--apply`.

## Test Category Decision

Covered:

- API contract tests: targeted Workbench V2 exception apply test preserves the
  endpoint behavior that creates the closed case and relation.
- Service-layer tests: Workbench write characterization test preserves duplicate
  exception apply idempotency at the HTTP boundary.
- Existing feature regression tests: static guards preserve route-owner
  registration, exception apply ownership, and Go admission blocking.

Not applicable:

- Business core unit tests: no exception rule, classifier or relation rule
  changed.
- Read model/cache/background job tests: no dirty scope, worker, cache or
  freshness semantics changed beyond preserving the existing guard.
- Frontend component/interaction tests: no frontend contract changed.
- End-to-end business-flow tests: targeted backend API/characterization coverage
  is sufficient for this ownership-only extraction.

## State Machine Impact

- `MODULE-QUEUE.md` row 196 should move from `pending` to
  `implementation-closed`.
- Add row 197 as `server-py:workbench-confirm-link-preview-route-owner-extraction`
  with `pending`.
- `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and
  `prompts/04-master-goal-controller.md` should point to row 197.
- Global state definitions in `03-REFACTOR-STATE-MACHINE.md` are unchanged.
- Module state-machine definitions are unchanged; module implementation notes
  record the route-owner ownership change.

## Verification

Target commands:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_exception_apply_api_creates_closed_case_and_pair_relation tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_duplicate_exception_apply_is_service_idempotent_at_http_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_exception_apply_mapping_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```
