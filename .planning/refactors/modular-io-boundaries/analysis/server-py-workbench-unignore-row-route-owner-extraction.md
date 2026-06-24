# server-py:workbench-unignore-row-route-owner-extraction

**Date:** 2026-06-24
**Status:** implementation-closed
**Previous boundary:** `server-py:workbench-ignore-row-route-owner-extraction`
**Next boundary:** `server-py:modern-workbench-action-route-owner-post-extraction-audit`

## Goal

Move modern `/api/workbench/actions/unignore-row` facade delegation out of `Application` and behind `WorkbenchActionApiRoutes`, while preserving the existing HTTP and write-response contract.

This is a narrow route-owner extraction slice. It does not change unignore-row business rules, exception case writes, read model refresh behavior, operation barrier targets, frontend behavior, legacy `/workbench/actions/*` behavior, or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-ignore-row-route-owner-extraction.md`
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

CodeGraph lookup for `unignore_row` confirmed the behavior owner remains `WorkbenchWriteFacade.unignore_row(...)`, with the route extraction adding only the `WorkbenchActionApiRoutes` ownership boundary.

## Change Summary

- Added `WorkbenchActionApiRoutes.unignore_row(...)`.
- Changed `Application._handle_workbench_unignore_row_payload(...)` to delegate through `_workbench_action_api_routes.unignore_row(payload)`.
- Kept `Application._handle_api_workbench_unignore_row(...)` responsible for JSON parsing and the Workbench write freshness guard.
- Added a static boundary guard proving:
  - the route owner exposes the `unignore_row` method;
  - the API wrapper keeps JSON parsing and freshness guard;
  - the helper keeps write-response mapping;
  - neither wrapper nor helper reintroduces a direct `Application`-owned `WorkbenchWriteFacade.unignore_row(...)` call.
- Removed the final remaining direct modern Workbench action facade exception from the legacy quarantine guard.

## Preserved Contract

- Invalid JSON remains handled by `Application._load_json_body(...)`.
- Workbench write freshness guard remains in `Application`.
- Existing `WorkbenchWriteFacade.unignore_row(...)` remains the business delegate through the route owner.
- Existing `_workbench_write_response(...)` mapping is unchanged.
- Conflict behavior, affected scopes, operation projection and operation barrier behavior are unchanged.
- No read model refresh, worker, repository, frontend, permission, audit or legacy `/workbench/actions/*` behavior changed.

## Legacy Path State

- Modern unignore-row facade delegation is now route-owner owned.
- Legacy `/workbench/actions/*` remains quarantined behind `LegacyWorkbenchActionRoutes`.
- No known modern Workbench action route in the audited set remains app-owned direct facade delegation.
- The next slice must audit post-extraction residuals before selecting more server ownership work.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rule or state transition changed.
2. Service-layer tests: not applicable for new coverage; behavior owner remains `WorkbenchWriteFacade`.
3. API contract tests: existing V2 API tests plus static route-owner guard protect JSON/freshness/response behavior.
4. Read model/cache/background job tests: existing ignore/unignore API tests cover invalidation/scheduling behavior; no read model code changed.
5. Frontend component and interaction tests: not applicable; no frontend contract changed.
6. End-to-end business-flow tests: not required for this route-owner-only extraction; broader Workbench relation e2e remains unchanged.
7. Existing feature regression tests: applicable through API and static boundary guards.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_workbench_write_characterization.WorkbenchWriteCharacterizationTests.test_duplicate_ignore_and_unignore_current_behavior tests.test_workbench_v2_api.WorkbenchV2ApiTests.test_ignore_and_unignore_invoice_moves_row_between_open_and_ignored_views tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_unignore_row_delegation_is_owned_by_action_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile backend/src/fin_ops_platform/app/routes_workbench_actions.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- Row 208 moves from `pending` to `implementation-closed`.
- Row 209 is added as the next pending boundary: `server-py:modern-workbench-action-route-owner-post-extraction-audit`.
- Module closure remains `implementation-gap-open`; this closes only one modern Workbench action route-owner slice.
