# server-py:workbench-withdraw-link-preview-route-owner-extraction

**Date:** 2026-06-24
**Status:** implementation-closed
**Previous boundary:** `server-py:modern-workbench-action-route-owner-post-extraction-audit`
**Next boundary:** `server-py:modern-workbench-action-route-owner-final-residual-audit`

## Goal

Move modern `/api/workbench/actions/withdraw-link/preview` facade delegation out of `Application` and behind `WorkbenchActionApiRoutes`, while preserving the existing HTTP and preview response contract.

This is a narrow route-owner extraction slice. It does not change withdraw preview business rules, relation preview identity, submit expected versions, operation type semantics, read model refresh behavior, operation barrier targets, frontend behavior, legacy `/workbench/actions/*` behavior, or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-post-extraction-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph lookup for `preview_withdraw_link` confirmed the behavior owner remains `WorkbenchWriteFacade.preview_withdraw_link(...)`, with the route extraction adding only the `WorkbenchActionApiRoutes` ownership boundary.

## Change Summary

- Added `WorkbenchActionApiRoutes.withdraw_link_preview(...)`.
- Changed `Application._handle_api_workbench_withdraw_link_preview(...)` to delegate through `_workbench_action_api_routes.withdraw_link_preview(payload)`.
- Kept `Application._handle_api_workbench_withdraw_link_preview(...)` responsible for JSON parsing and `_workbench_write_response(...)`.
- Added a static boundary guard proving:
  - the route owner exposes the `withdraw_link_preview` method;
  - the API wrapper keeps JSON parsing and write response mapping;
  - the wrapper does not reintroduce a direct `Application`-owned `WorkbenchWriteFacade.preview_withdraw_link(...)` call.

## Preserved Contract

- Invalid JSON remains handled by `Application._load_json_body(...)`.
- Existing `WorkbenchWriteFacade.preview_withdraw_link(...)` remains the business delegate through the route owner.
- Existing `_workbench_write_response(...)` mapping is unchanged.
- Preview response shape, conflict behavior, preview id/version semantics, operation type semantics and downstream operation-barrier behavior are unchanged.
- No read model refresh, worker, repository, frontend, permission, audit or legacy `/workbench/actions/*` behavior changed.

## Legacy Path State

- Modern withdraw-link preview facade delegation is now route-owner owned.
- Legacy `/workbench/actions/*` remains quarantined behind `LegacyWorkbenchActionRoutes`.
- The next slice must re-audit modern Workbench action residuals before selecting more server ownership work.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rule or state transition changed.
2. Service-layer tests: not applicable for new coverage; behavior owner remains `WorkbenchWriteFacade`.
3. API contract tests: existing withdraw preview API/characterization tests plus static route-owner guard protect JSON/response behavior.
4. Read model/cache/background job tests: not applicable for new coverage; no read model code changed.
5. Frontend component and interaction tests: not applicable; no frontend contract changed.
6. End-to-end business-flow tests: not required for this route-owner-only extraction; broader Workbench relation e2e remains unchanged.
7. Existing feature regression tests: applicable through API and static boundary guards.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_withdraw_link_preview_splits_reconciliation_decision_without_active_relation tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_stale_withdraw_preview_withdraws_current_relation_without_restoring_same_row_set tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_withdraw_link_preview_delegation_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_withdraw_link_preview_route_owner_extraction_updates_queue tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_modern_workbench_action_route_owner_post_extraction_audit_selects_withdraw_preview tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- Row 210 moves from `pending` to `implementation-closed`.
- Row 211 is added as the next pending boundary: `server-py:modern-workbench-action-route-owner-final-residual-audit`.
- Module closure remains `implementation-gap-open`; this closes only one modern Workbench action route-owner slice.
