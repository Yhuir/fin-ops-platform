# server-py:workbench-personal-advance-repayment-route-owner-extraction

**Date:** 2026-06-24
**Status:** implementation-closed
**Previous boundary:** `server-py:workbench-oa-bank-exception-route-owner-extraction`
**Next boundary:** `server-py:workbench-cancel-exception-route-owner-extraction`

## Goal

Move modern `/api/workbench/actions/confirm-personal-advance-repayment` facade delegation out of `Application` and behind `WorkbenchActionApiRoutes`, while preserving the existing HTTP, request-id and write-response contract.

This is a narrow route-owner extraction slice. It does not change personal advance settlement business rules, relation writes, read model refresh behavior, operation barrier targets, frontend behavior, legacy `/workbench/actions/*` behavior, or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-oa-bank-exception-route-owner-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/state-machine.md`
- `docs/modules/workbench-relations/tests.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph lookup for `confirm_personal_advance_repayment` confirmed the behavior owner remains `WorkbenchWriteFacade.confirm_personal_advance_repayment(...)`, with the route extraction adding only the `WorkbenchActionApiRoutes` ownership boundary.

## Change Summary

- Added `WorkbenchActionApiRoutes.confirm_personal_advance_repayment(...)`.
- Changed `Application._handle_api_workbench_confirm_personal_advance_repayment(...)` to delegate through `_workbench_action_api_routes.confirm_personal_advance_repayment(payload, request_id=request_id)`.
- Changed `Application._handle_live_workbench_confirm_personal_advance_repayment(...)` to delegate through `_workbench_action_api_routes.confirm_personal_advance_repayment(payload, request_id=request_id)`.
- Added a static boundary guard proving:
  - the route owner exposes the `confirm_personal_advance_repayment` method;
  - request-id forwarding remains preserved;
  - the API wrapper keeps JSON parsing, freshness guard and write-response mapping;
  - the live helper keeps write-response mapping;
  - neither wrapper reintroduces a direct `Application`-owned `WorkbenchWriteFacade.confirm_personal_advance_repayment(...)` call.
- Narrowed the legacy quarantine guard so personal advance repayment is no longer classified as an app-owned direct facade path.

## Preserved Contract

- Invalid JSON remains handled by `Application._load_json_body(...)`.
- Workbench write freshness guard remains in `Application`.
- Existing `WorkbenchWriteFacade.confirm_personal_advance_repayment(...)` remains the business delegate through the route owner.
- Existing `request_id` forwarding and `_workbench_write_response(...)` mapping are unchanged.
- Duplicate behavior, not-found behavior, persistence failure behavior, scheduling failure behavior, affected scopes, operation projection and operation barrier behavior are unchanged.
- No read model refresh, worker, repository, frontend, permission, audit or legacy `/workbench/actions/*` behavior changed.

## Legacy Path State

- Modern personal advance repayment facade delegation is now route-owner owned.
- Legacy `/workbench/actions/*` remains quarantined behind `LegacyWorkbenchActionRoutes`.
- Remaining modern app-owned facade wrappers are intentionally left for later slices: cancel exception, ignore and unignore.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rule or state transition changed.
2. Service-layer tests: existing characterization tests remain applicable because the facade behavior is preserved.
3. API contract tests: existing V2 API tests plus static route-owner guard protect JSON/freshness/request-id/response behavior.
4. Read model/cache/background job tests: existing personal advance characterization and API tests cover persistence/scheduling side effects; no read model code changed.
5. Frontend component and interaction tests: not applicable; no frontend contract changed.
6. End-to-end business-flow tests: not required for this route-owner-only extraction; broader Workbench relation e2e remains unchanged.
7. Existing feature regression tests: applicable through characterization, API and static boundary guards.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_duplicate_personal_advance_repayment_returns_not_found_after_first_settlement_current_behavior tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_stale_personal_advance_after_exception_returns_not_found_and_preserves_exception tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_personal_advance_persistence_failure_rolls_back_exception_case_and_relation tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_personal_advance_scheduling_failure_propagates_after_case_and_relation_are_mutated tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_confirm_personal_advance_repayment_rejects_unbalanced_amounts tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_personal_advance_repayment_delegation_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- Row 205 moves from `pending` to `implementation-closed`.
- Row 206 is added as the next pending boundary: `server-py:workbench-cancel-exception-route-owner-extraction`.
- Module closure remains `implementation-gap-open`; this closes only one modern Workbench action route-owner slice.
