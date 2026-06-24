# server-py:modern-workbench-action-route-owner-post-extraction-audit

**Date:** 2026-06-24
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-unignore-row-route-owner-extraction`
**Next boundary:** `server-py:workbench-withdraw-link-preview-route-owner-extraction`

## Goal

Audit the modern Workbench action route-owner extraction after ignore-row and unignore-row closure, verify whether app-owned direct `WorkbenchWriteFacade` action delegation remains, and select the next bounded server ownership slice.

This is an audit slice. It does not change runtime behavior, route wiring, response shape, read model refresh behavior, operation barrier behavior, frontend behavior, legacy `/workbench/actions/*` behavior, or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-unignore-row-route-owner-extraction.md`
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

CodeGraph and literal search were used to inspect the modern Workbench action wrapper surface.

## Findings

Modern route-owner extraction is materially improved but not fully closed:

- `WorkbenchActionApiRoutes` owns the modern facade delegation for exception preview/apply, confirm-link preview/submit, mark-exception, cancel-link, withdraw-link submit, cash special actions, update-bank-exception, OA-bank-exception, personal advance repayment, cancel-exception, ignore-row and unignore-row.
- `LegacyWorkbenchActionRoutes` remains compat-only for old `/workbench/actions/confirm|difference|exception|offline|offset` and does not import `WorkbenchWriteFacade`, `WorkbenchRelationCommandService`, `ReadModelRefreshGateway`, `job.outbox_events`, or `job.read_model_dirty_scopes`.
- `Application` still owns acceptable HTTP concerns for the migrated modern wrappers: dispatch, JSON parsing, freshness guard, auth/request context where already present, request timing where already present, and response serialization.
- One app-owned direct facade delegation remains in the audited modern action surface:
  - `Application._handle_api_workbench_withdraw_link_preview(...)` still calls `self._workbench_write_facade().preview_withdraw_link(payload)`.

## Residual Boundary

`POST /api/workbench/actions/withdraw-link/preview` should be the next bounded implementation slice.

Rationale:

- The route was already classified in the modern action audit as a target for modern action preview route ownership.
- It has a narrow responsibility set: JSON parse in `Application`, `WorkbenchWriteFacade.preview_withdraw_link(...)` delegation, and `_workbench_write_response(...)` mapping.
- Existing tests cover withdraw preview scenarios in `tests/test_workbench_v2_api.py` and `tests/test_workbench_write_characterization.py`.
- Extracting it continues the same route-owner direction without changing relation write semantics, freshness guard behavior, operation barrier behavior, read model refresh behavior, frontend behavior or legacy route behavior.

## Non-Goals

- Do not remove the cancel-exception live-service no-op branch in this audit.
- Do not move additional routes in this audit.
- Do not introduce shared route helper abstractions without a concrete duplication problem beyond this route.
- Do not implement Go, Go Fiber or Go Worker.
- Do not mark Workbench relations or server route ownership globally closed.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rule or state transition changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: existing tests are evidence for the selected next slice; no API contract changed in this audit.
4. Read model/cache/background job tests: not applicable; no read model, cache or worker behavior changed.
5. Frontend component and interaction tests: not applicable; no frontend behavior changed.
6. End-to-end business-flow tests: not required for this audit; no runtime behavior changed.
7. Existing feature regression tests: applicable through static route-owner/state-machine guards.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner -v
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- Row 209 moves from `pending` to `analysis-closed`.
- Row 210 is added as the next pending boundary: `server-py:workbench-withdraw-link-preview-route-owner-extraction`.
- Module closure remains `implementation-gap-open`; this audit finds one remaining modern action preview route-owner implementation gap.
