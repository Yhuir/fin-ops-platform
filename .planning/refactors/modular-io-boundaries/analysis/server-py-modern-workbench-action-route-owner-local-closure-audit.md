# server-py:modern-workbench-action-route-owner-local-closure-audit

**Date:** 2026-06-24
**Status:** analysis-closed
**Previous boundary:** `server-py:workbench-cancel-exception-live-dispatch-noop-cleanup`
**Next boundary:** `server-py:workbench-row-detail-route-owner-audit`

## Goal

Audit whether the modern Workbench action route-owner slice set has local closure evidence after the final direct facade residual and cancel-exception no-op cleanup slices.

This is a local closure audit for the modern action route-owner surface only. It does not change runtime behavior, route wiring, response shape, read model refresh behavior, operation barrier behavior, frontend behavior, legacy `/workbench/actions/*` behavior, production state, or Go/Fiber/Go Worker admission.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/autonomous/MODULE-QUEUE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/STATE.md`
- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-cancel-exception-live-dispatch-noop-cleanup.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-final-residual-audit.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
- `backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py`
- `tests/test_platform_runtime_boundary_guards.py`
- CodeGraph context for Workbench action route-owner and server ownership surfaces.

## Local Closure Findings

The modern Workbench action route-owner slice set has local closure evidence for the audited action surface:

- `WorkbenchActionApiRoutes` owns the modern action delegation for exception preview/apply, confirm-link preview/submit, mark-exception, cancel-link, withdraw-link preview/submit, cash special actions, update-bank-exception, OA-bank-exception, personal advance repayment, cancel-exception, ignore-row and unignore-row.
- `Application` keeps only the accepted HTTP wrapper responsibilities for these actions: route dispatch, JSON body parsing, existing freshness guard, existing auth/request context, existing timing, and response serialization.
- Literal search for `_workbench_write_facade().` in `server.py`, `routes_workbench_actions.py` and `routes_legacy_workbench_actions.py` found no remaining direct app-owned modern action facade call sites.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset` as a compat-only route owner and does not import or call `WorkbenchActionApiRoutes`, `WorkbenchWriteFacade`, relation command services, read model refresh, dirty scope or outbox boundaries.
- The redundant cancel-exception `has_rows_for_month(...)` branch has been removed, so the modern cancel-exception wrapper no longer contains the last audited no-op live dispatch branch.
- Existing static guards in `tests/test_platform_runtime_boundary_guards.py` cover each modern action delegate, legacy action quarantine, direct facade absence for action wrappers/helpers, and the corrected queue accounting.

## Not Global Closure

This audit closes only the modern Workbench action route-owner local slice. It does not close Workbench, server.py, read model, worker, relation, frontend or production validation globally.

Known remaining server ownership surfaces outside this action route-owner slice include:

- `GET /api/workbench`, summary, groups page, group detail, refresh status and events handlers.
- `GET /api/workbench/rows/{row_id}` row detail handler and fallback chain.
- Workbench settings, manual search/import, project sync and data reset handlers.
- Workbench read model enqueue/status, Redis group cache, active generation build/persist, matching dirty-scope, raw payload, ignored rows and source-version helpers.
- Legacy-compatible Workbench wrapper helpers that remain acceptable only if they keep delegating through explicit route/service boundaries and do not re-own business rules or refresh state.

No module can be marked `closed` from this audit because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.

## Next Boundary

The next bounded server ownership slice should be:

`server-py:workbench-row-detail-route-owner-audit`

Rationale:

- `docs/modules/reconciliation-workbench/README.md` explicitly defines `GET /api/workbench/rows/{row_id}` as a row detail read interface that must prefer live/cache, fall back through `WorkbenchQueryFacade`, and never write relation state.
- The row detail path is still owned by `Application._handle_api_workbench_row_detail(...)`, `_get_api_workbench_row_detail_payload(...)`, `_workbench_row_detail_from_query_facade(...)` and `_workbench_row_detail_route_fallback_allowed(...)`.
- It is narrower than all Workbench read/query ownership and safer than starting a broad `server.py` cleanup.
- It directly advances the same server ownership goal after the action route-owner surface is locally closed.

## Non-Goals

- Do not move the row detail route in this audit.
- Do not change `GET /api/workbench/rows/{row_id}` response shape, fallback order, status codes, stale/fresh behavior, override application, or SQL runtime fallback semantics in the local closure audit.
- Do not change groups, refresh status, Workbench settings, active generation publishing, matching worker, read model queue, frontend behavior, or legacy `/workbench/actions/*` behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

## Seven Test Category Decision

1. Business core unit tests: not applicable; no business rule or state transition changed.
2. Service-layer tests: not applicable; no service behavior changed.
3. API contract tests: existing route-owner/static guards protect the current action API ownership; no API response shape changed in this audit.
4. Read model/cache/background job tests: not applicable for this audit; no read model, cache or worker behavior changed.
5. Frontend component and interaction tests: not applicable; no frontend behavior changed.
6. End-to-end business-flow tests: not required for this audit; no runtime behavior changed.
7. Existing feature regression tests: applicable through static route-owner, legacy quarantine and state-machine guards.

## Verification

Target verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_modern_workbench_action_route_owner_local_closure_audit_selects_row_detail_audit tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_cancel_exception_noop_cleanup_updates_queue tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_legacy_workbench_actions_stay_quarantined_in_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
python3 -m py_compile tests/test_platform_runtime_boundary_guards.py
bash scripts/verify.sh docs
git diff --check
```

## State Impact

- Row 213 moves from `pending` to `analysis-closed`.
- Row 214 is added as the next pending boundary: `server-py:workbench-row-detail-route-owner-audit`.
- Module closure remains `implementation-gap-open`; this audit closes only the modern Workbench action route-owner local closure question.
