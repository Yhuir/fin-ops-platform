# server-py Workbench confirm-link preview route owner extraction

Date: 2026-06-24
Boundary: `server-py:workbench-confirm-link-preview-route-owner-extraction`
Status: `implementation-closed`

## Goal

Move `/api/workbench/actions/confirm-link/preview` facade delegation and
invalid-request mapping out of `Application` and behind
`WorkbenchActionApiRoutes`, while preserving the existing app-level JSON body
parsing and response serialization.

## Changes

- Added `WorkbenchActionApiRoutes.confirm_link_preview(...)`.
- Moved `WorkbenchWriteFacade.preview_confirm_link(...)` invocation and
  `KeyError` / `TypeError` / `ValueError` to
  `invalid_confirm_link_preview_request` mapping into the route owner.
- Kept `Application._handle_api_workbench_confirm_link_preview(...)`
  responsible for JSON body parsing and `_json_response(...)` serialization.
- Added a static guard proving confirm-link preview delegation and error
  mapping are route-owned and the app wrapper still serializes the owner result.

## Preserved Contract

- Invalid JSON is still handled by `Application._load_json_body(...)`.
- Delegate remains `WorkbenchWriteFacade.preview_confirm_link(...)`.
- `KeyError`, `TypeError` and `ValueError` still map to HTTP 400 with
  `error="invalid_confirm_link_preview_request"`.
- Successful preview still maps to HTTP 200 with the existing preview payload.
- No confirm submit, auth, freshness guard, request timing, relation write
  semantics, operation barrier, read model refresh, frontend API or legacy route
  behavior changed.

## Non-Goals

- Did not move confirm submit, cancel, withdraw, cash special, bank exception,
  OA-bank exception, personal advance repayment, cancel exception, ignore,
  unignore, exception preview or exception apply routes.
- Did not change legacy `/workbench/actions/*`.
- Did not implement Go, Go Fiber or Go Worker.
- Did not perform production writes, deploy, restart services, requeue jobs,
  mark scopes done, mutate readiness or run repair tools with `--apply`.

## Test Category Decision

Covered:

- API contract tests: targeted Workbench V2 confirm-link preview tests preserve
  mismatch note, mixed bank direction, existing-case before-state and
  already-active withdraw-preview behavior.
- Existing feature regression tests: static guards preserve route-owner
  ownership and Go admission blocking.

Not applicable:

- Business core unit tests: no amount rule, grouping rule, state transition or
  relation rule changed.
- Service-layer tests: no service contract changed; the facade delegate remains
  unchanged.
- Read model/cache/background job tests: no dirty scope, worker, cache,
  operation barrier or freshness semantics changed.
- Frontend component/interaction tests: no frontend contract changed.
- End-to-end business-flow tests: targeted backend API coverage is sufficient
  for this ownership-only preview extraction.

## State Machine Impact

- `MODULE-QUEUE.md` row 197 should move from `pending` to
  `implementation-closed`.
- Add row 198 as `server-py:workbench-confirm-link-submit-route-owner-extraction`
  with `pending`.
- `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and
  `prompts/04-master-goal-controller.md` should point to row 198.
- Global state definitions in `03-REFACTOR-STATE-MACHINE.md` are unchanged.
- Module state-machine definitions are unchanged; module implementation notes
  record the route-owner ownership change.

## Verification

Target commands:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_and_submit_require_note_for_amount_mismatch tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_uses_directional_bank_total_for_mixed_bank_directions tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_preserves_existing_case_group_before_submit tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_link_preview_for_already_active_relation_returns_withdraw_preview tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_confirm_link_preview_mapping_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```
