# server-py:modern-workbench-action-route-owner-final-residual-audit

**Date:** 2026-06-24
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-withdraw-link-preview-route-owner-extraction`
**Next boundary:** `server-py:workbench-cancel-exception-live-dispatch-noop-cleanup`

## Goal

Re-audit the modern Workbench action route-owner extraction after withdraw-link preview closure, verify whether app-owned direct `WorkbenchWriteFacade` action delegation remains, and select the next bounded server ownership slice.

This is an audit slice. It does not change runtime behavior, route wiring, response shape, read model refresh behavior, operation barrier behavior, frontend behavior, legacy `/workbench/actions/*` behavior, or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-withdraw-link-preview-route-owner-extraction.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-post-extraction-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
- `backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Findings

The audited modern Workbench action route-owner extraction has no remaining app-owned direct `WorkbenchWriteFacade` action delegation:

- Literal search for `_workbench_write_facade().` in `server.py`, `routes_workbench_actions.py` and `routes_legacy_workbench_actions.py` found no remaining direct action call sites.
- `WorkbenchActionApiRoutes` exposes all audited modern action delegates: exception preview/apply, confirm-link preview/submit, mark-exception, cancel-link, withdraw-link preview/submit, cash special actions, update-bank-exception, OA-bank-exception, personal advance repayment, cancel-exception, ignore-row and unignore-row.
- `Application` still owns acceptable HTTP concerns for these routes: dispatch, JSON parsing, freshness guard where already present, auth/request context where already present, request timing where already present, and response serialization.
- `LegacyWorkbenchActionRoutes` remains compat-only for old `/workbench/actions/confirm|difference|exception|offline|offset` and does not import modern write facade, relation command, read model refresh, outbox or dirty scope boundaries.

## Residual Boundary

The next bounded server ownership slice should be:

`server-py:workbench-cancel-exception-live-dispatch-noop-cleanup`

Rationale:

- `Application._handle_api_workbench_cancel_exception(...)` still has a no-op `has_rows_for_month(month)` branch where both branches call `_handle_live_workbench_cancel_exception(payload)`.
- This no-op branch was explicitly recorded in the original modern Workbench action route-owner audit as a later cleanup candidate.
- Removing it is narrow and should not change response shape, freshness guard behavior, operation barrier behavior, read model refresh behavior, frontend behavior or legacy route behavior.
- The slice should preserve JSON parsing, freshness guard and `_handle_live_workbench_cancel_exception(payload)` response mapping.

## Non-Goals

- Do not move additional routes in this audit.
- Do not remove the cancel-exception live-service no-op branch in this audit.
- Do not mark Workbench relations or server route ownership globally closed.
- Do not implement Go, Go Fiber or Go Worker.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rule or state transition changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: existing cancel-exception tests are evidence for the selected next slice; no API contract changed in this audit.
4. Read model/cache/background job tests: not applicable; no read model, cache or worker behavior changed.
5. Frontend component and interaction tests: not applicable; no frontend behavior changed.
6. End-to-end business-flow tests: not required for this audit; no runtime behavior changed.
7. Existing feature regression tests: applicable through static route-owner/state-machine guards.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_withdraw_link_preview_route_owner_extraction_updates_queue tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- Row 211 moves from `pending` to `analysis-closed`.
- Row 212 is added as the next pending boundary: `server-py:workbench-cancel-exception-live-dispatch-noop-cleanup`.
- Module closure remains `implementation-gap-open`; this audit only closes the direct facade residual question for the audited modern action surface.
