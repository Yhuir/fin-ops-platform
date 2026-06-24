# Workbench Legacy Action Handler Quarantine Audit

**Date:** 2026-06-24
**Boundary:** `server-py:workbench-legacy-action-handler-quarantine-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit Workbench legacy action handlers in `server.py` before any code movement. Classify each target handler by caller, write owner, read model/worker side effects, delegation boundary and target state.

This slice does not move, delete or rewrite runtime code.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/analysis/server-py-residual-route-handler-boundary-audit.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_app.py`
- `tests/test_ledger_api.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_auth_context_idempotency.py`
- `tests/test_platform_runtime_boundary_guards.py`

## Handler Classification

| Handler group | Current caller | Current write/delegation | Test evidence | Target state |
| --- | --- | --- | --- | --- |
| `_handle_workbench_confirm`, `_handle_workbench_difference`, `_handle_workbench_exception`, `_handle_workbench_offline`, `_handle_workbench_offset` | Legacy untracked routes: `POST /workbench/actions/confirm`, `/difference`, `/exception`, `/offline`, `/offset` from `_handle_request_untracked(...)` | Directly calls `ManualReconciliationService` methods and, for confirm/exception/offline, `LedgerService.sync_from_case(...)`. This is old ledger/follow-up behavior, not modern Workbench relation command behavior. | `tests/test_ledger_api.py` still posts to `/workbench/actions/confirm` and `/workbench/actions/exception`; `tests/test_app.py` still lists `/workbench/actions/difference` and `/workbench/actions/offset` in health entrypoints. | `compat-only quarantine`. Do not merge into modern `/api/workbench/actions/*`. First implementation boundary should isolate these legacy endpoints behind an explicit legacy route owner and guard that they cannot call modern relation/read model writers directly. Later deletion requires ledger replacement evidence. |
| `_handle_legacy_workbench_exception_via_application(...)` | No current route dispatch found in `server.py`; retained helper delegates to `WorkbenchExceptionApplicationService.preview(...)` and `_apply_workbench_exception_application(...)` | Application-service path, not direct `ManualReconciliationService`. It still lives in `server.py` and overlaps the modern `/api/workbench/exception/apply` path. | No direct test or route reference found by literal search; modern exception tests cover `/api/workbench/exception/*` and live facade wrappers. | `blocked-by-caller-evidence`. Next audit after legacy route quarantine should prove whether this helper is dead and removable, or make it a compat-only internal delegate with a deletion condition. |
| `_handle_live_workbench_confirm_link`, `_handle_live_workbench_cancel_link`, `_handle_live_workbench_withdraw_link` | Modern API wrappers via `_handle_api_workbench_confirm_link(...)`, `_handle_api_workbench_cancel_link(...)`; withdraw API calls facade directly instead of the listed live wrapper | Delegates to `WorkbenchWriteFacade.confirm_link/cancel_link/withdraw_link(...)`, which is the current port/command-service boundary. | `tests/test_workbench_v2_api.py`, `tests/test_workbench_auth_context_idempotency.py`, `tests/test_workbench_write_characterization.py` and e2e specs cover `/api/workbench/actions/confirm-link`, `/cancel-link`, `/withdraw-link`. | `route-owned delegate`. Keep behavior, but later route-module migration should move HTTP parsing/auth/timing into a proper Workbench route owner without touching relation semantics. |
| `_handle_live_workbench_mark_exception`, `_handle_live_workbench_update_bank_exception`, `_handle_live_workbench_oa_bank_exception`, `_handle_live_workbench_confirm_personal_advance_repayment`, `_handle_live_workbench_cancel_exception`, `_handle_workbench_ignore_row_payload`, `_handle_workbench_unignore_row_payload` | Modern API wrappers under `/api/workbench/actions/*` | Delegates to `WorkbenchWriteFacade` methods. This is already separated from old `ManualReconciliationService`; facade internally uses explicit read/snapshot and special-metadata ports plus command service where implemented. | Workbench v2, exception, permission and Browser smoke tests cover modern endpoints. | `route-owned delegate`. Keep as modern route wrappers; later route-module extraction is safe only with existing API contract tests. |

## Key Findings

1. The dangerous old chain is not the modern `/api/workbench/actions/*` facade path. It is the legacy `/workbench/actions/*` path still registered in `_handle_request_untracked(...)`.
2. The legacy `/workbench/actions/*` handlers directly call `ManualReconciliationService` and `LedgerService`. They do not use `WorkbenchRelationCommandService`, `WorkbenchWriteFacade`, read model operation barriers or the modern Workbench action API contract.
3. The legacy chain is still observable through tests:
   - `tests/test_ledger_api.py` validates ledger creation and reminder flows through `/workbench/actions/confirm` and `/workbench/actions/exception`.
   - `tests/test_app.py` advertises `/workbench/actions/difference` and `/workbench/actions/offset` in `/health` entrypoints.
4. Because tests still depend on these routes, direct deletion would be unsafe in this slice. The correct next move is quarantine: isolate these old endpoints under an explicit legacy route owner and add guards that prevent them from being mistaken for modern Workbench relation/read model paths.
5. `routes_workbench.py` is currently too thin and only delegates basic `WorkbenchActionService` calls. It is not the right owner for the legacy ledger action semantics unless the legacy behavior is intentionally ported or retired.

## Next Selected Boundary

`server-py:legacy-workbench-action-route-module-quarantine`

Scope:

- Create an explicit legacy Workbench action route owner for the old `/workbench/actions/confirm`, `/difference`, `/exception`, `/offline`, and `/offset` handlers.
- Move only HTTP/payload mapping for those old endpoints out of the large `Application` request dispatcher surface.
- Preserve current legacy endpoint behavior and tests in this boundary.
- Add a static guard that:
  - legacy `/workbench/actions/*` remains classified as compat-only,
  - modern `/api/workbench/actions/*` continues to use `WorkbenchWriteFacade`,
  - the old handlers are not advertised as modern Workbench relation/read model endpoints,
  - no Go/Fiber/Go Worker implementation starts.
- Do not migrate ledger semantics, relation writes, read model refreshes or frontend APIs in the same boundary.

Rationale:

- This is the smallest implementation slice that reduces old-code pollution without changing business semantics.
- It creates a clear boundary for later deletion or replacement of the legacy ledger path.
- It keeps the modern modular IO direction intact: old Workbench actions become isolated compat-only behavior, while modern Workbench writes stay behind facade/command/service boundaries.

## State Machine Impact

- `server-py:workbench-legacy-action-handler-quarantine-audit` transitions to `analysis-closed`.
- Insert `server-py:legacy-workbench-action-route-module-quarantine` as the next pending boundary.
- Go/Fiber/Go Worker admission remains blocked.
- Global state-machine definitions are unchanged; this is an analysis/accounting slice covered by the existing `analysis-closed` label.
- No module state-machine definitions changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rule changed. |
| 2. Service-layer tests | Not applicable | No service behavior changed. |
| 3. API contract tests | Not applicable | No API route, response shape, status or permission behavior changed. |
| 4. Read model/cache/background job tests | Not applicable | No read model, queue, cache or worker behavior changed. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No runtime flow changed. |
| 7. Existing feature regression tests | Applicable | Platform guard should keep the autonomous queue pointing at the selected legacy route quarantine boundary and keep Go blocked. |

## Verification

Targeted verification for this slice:

```bash
PYTHONPATH=backend/src python3 -m unittest \
  tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded \
  -v

bash scripts/verify.sh docs
git diff --check
```

## Remaining Risk

- The legacy `/workbench/actions/*` runtime behavior still exists after this audit. It remains a compatibility path until the next implementation slice isolates it.
- `tests/test_ledger_api.py` still validates old ledger behavior through legacy Workbench routes. A later deletion must first provide an equivalent ledger/follow-up route or intentionally retire that capability.
- `_handle_legacy_workbench_exception_via_application(...)` has no current caller evidence in this audit but was not removed. It needs a separate dead-code/removal audit after legacy route quarantine.
