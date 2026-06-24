# server-py modern Workbench action route owner audit

Date: 2026-06-24
Boundary: `server-py:modern-workbench-action-route-owner-audit`
Status: `analysis-closed`

## Goal

Audit the modern Workbench write/action wrappers still owned by `Application` in
`backend/src/fin_ops_platform/app/server.py`, classify their IO boundary
responsibilities, and select the next narrow implementation boundary without
changing runtime behavior.

This slice is not a full route extraction and does not claim Workbench action
module closure.

## Evidence Read

- `.planning/refactors/modular-io-boundaries/analysis/server-py-legacy-workbench-action-route-module-quarantine.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-legacy-workbench-exception-helper-dead-code-audit.md`
- `docs/modules/reconciliation-workbench/README.md`
- `docs/modules/reconciliation-workbench/tests.md`
- `docs/modules/workbench-relations/README.md`
- `docs/modules/workbench-relations/implementation-notes.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `backend/src/fin_ops_platform/services/workbench_write_facade.py`
- `tests/test_workbench_v2_api.py`
- `tests/test_workbench_write_characterization.py`
- `tests/test_platform_runtime_boundary_guards.py`

CodeGraph also confirmed the current split:

- `LegacyWorkbenchActionRoutes` owns old compat `/workbench/actions/*` routes.
- `routes_workbench.py` still wraps older `WorkbenchActionService` methods and is not the current owner for modern `WorkbenchWriteFacade` action routes.
- Modern write behavior is currently reached through `Application` wrappers delegating to `WorkbenchWriteFacade` or `WorkbenchExceptionApplicationService`.

## Wrapper Classification

| API wrapper | Route | Current wrapper responsibilities | Delegate | Existing coverage | Target owner direction |
| --- | --- | --- | --- | --- | --- |
| `_handle_api_workbench_confirm_link` | `POST /api/workbench/actions/confirm-link` | JSON parse, freshness guard, auth context, request timing via dispatcher | `_handle_live_workbench_confirm_link` -> `WorkbenchWriteFacade.confirm_link` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Modern action route owner with shared freshness/auth/timing helpers |
| `_handle_api_workbench_confirm_link_preview` | `POST /api/workbench/actions/confirm-link/preview` | JSON parse, bad-request mapping | `WorkbenchWriteFacade.preview_confirm_link` | `tests/test_workbench_v2_api.py` | Modern action preview route owner |
| `_handle_api_workbench_exception_preview` | `POST /api/workbench/exception/preview` | JSON parse, not-found and bad-request mapping | `WorkbenchExceptionApplicationService.preview` | `tests/test_workbench_v2_api.py` | First extraction candidate because it has no freshness/auth/request-timing coupling |
| `_handle_api_workbench_exception_apply` | `POST /api/workbench/exception/apply` | JSON parse, freshness guard, actor derivation, request id | `WorkbenchWriteFacade.apply_exception` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Same future route owner as exception preview, but after preview extraction |
| `_handle_api_workbench_mark_exception` | `POST /api/workbench/actions/mark-exception` | JSON parse, freshness guard | `_handle_live_workbench_mark_exception` -> `WorkbenchWriteFacade.mark_exception` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Modern action route owner after exception preview/apply |
| `_handle_api_workbench_cancel_link` | `POST /api/workbench/actions/cancel-link` | JSON parse, freshness guard, auth context, request timing via dispatcher | `_handle_live_workbench_cancel_link` -> `WorkbenchWriteFacade.cancel_link` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Modern action route owner with shared freshness/auth/timing helpers |
| `_handle_api_workbench_withdraw_link_preview` | `POST /api/workbench/actions/withdraw-link/preview` | JSON parse, write-response mapping | `WorkbenchWriteFacade.preview_withdraw_link` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Modern action preview route owner |
| `_handle_api_workbench_withdraw_link` | `POST /api/workbench/actions/withdraw-link` | JSON parse, freshness guard, auth context, request timing via dispatcher | `WorkbenchWriteFacade.withdraw_link` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Modern action route owner with shared freshness/auth/timing helpers |
| `_handle_api_workbench_confirm_cash_pass_through` | `POST /api/workbench/actions/confirm-cash-pass-through` | JSON parse, freshness guard, request id | `WorkbenchWriteFacade.confirm_cash_pass_through` | `tests/test_workbench_write_characterization.py`, Workbench e2e smoke coverage in module docs | Modern action route owner after core relation paths |
| `_handle_api_workbench_confirm_cash_ticket_purchase` | `POST /api/workbench/actions/confirm-cash-ticket-purchase` | JSON parse, freshness guard, request id | `WorkbenchWriteFacade.confirm_cash_ticket_purchase` | `tests/test_workbench_write_characterization.py`, Workbench e2e smoke coverage in module docs | Modern action route owner after core relation paths |
| `_handle_api_workbench_cancel_cash_special` | `POST /api/workbench/actions/cancel-cash-special` | JSON parse, freshness guard, request id | `WorkbenchWriteFacade.cancel_cash_special` | `tests/test_workbench_write_characterization.py`, Workbench e2e smoke coverage in module docs | Modern action route owner after core relation paths |
| `_handle_api_workbench_update_bank_exception` | `POST /api/workbench/actions/update-bank-exception` | JSON parse, freshness guard | `WorkbenchWriteFacade.update_bank_exception` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Modern action route owner |
| `_handle_api_workbench_oa_bank_exception` | `POST /api/workbench/actions/oa-bank-exception` | JSON parse, freshness guard | `WorkbenchWriteFacade.oa_bank_exception` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Modern action route owner |
| `_handle_api_workbench_confirm_personal_advance_repayment` | `POST /api/workbench/actions/confirm-personal-advance-repayment` | JSON parse, freshness guard, request id | `WorkbenchWriteFacade.confirm_personal_advance_repayment` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py` | Modern action route owner |
| `_handle_api_workbench_cancel_exception` | `POST /api/workbench/actions/cancel-exception` | JSON parse, freshness guard; contains a no-op `has_rows_for_month(...)` branch whose both branches call the same delegate | `_handle_live_workbench_cancel_exception` -> `WorkbenchWriteFacade.cancel_exception` | module e2e smoke coverage and Workbench action characterization adjacency | Modern action route owner; no-op branch can be removed in a later cleanup slice |
| `_handle_api_workbench_ignore_row` | `POST /api/workbench/actions/ignore-row` | JSON parse, freshness guard | `_handle_workbench_ignore_row_payload` -> `WorkbenchWriteFacade.ignore_row` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py`, module e2e smoke coverage | Modern action route owner |
| `_handle_api_workbench_unignore_row` | `POST /api/workbench/actions/unignore-row` | JSON parse, freshness guard | `_handle_workbench_unignore_row_payload` -> `WorkbenchWriteFacade.unignore_row` | `tests/test_workbench_v2_api.py`, `tests/test_workbench_write_characterization.py`, module e2e smoke coverage | Modern action route owner |

## Observations

- Old `/workbench/actions/confirm|difference|exception|offline|offset` endpoints are now explicitly owned by `LegacyWorkbenchActionRoutes` and must stay compat-only until retired.
- Modern `/api/workbench/actions/*` wrappers do not call `ManualReconciliationService`; they delegate to `WorkbenchWriteFacade`.
- `routes_workbench.py` is not a safe target for blindly adding these routes because it still wraps `WorkbenchActionService`, while modern routes rely on `WorkbenchWriteFacade`, freshness guards, auth context, request id, and `WorkbenchExceptionApplicationService`.
- The first route-owner implementation should therefore introduce or extend a modern action route owner around the current facade/application-service delegates, not mix modern routes into the old action-service route owner.
- `_handle_api_workbench_cancel_exception(...)` has a redundant live-service branch, but removing that branch is smaller than the route-owner goal and can be handled after the first modern route owner pattern is established.

## Selected Next Boundary

`server-py:workbench-exception-preview-route-owner-extraction`

Rationale:

- It moves one real modern endpoint toward route ownership.
- It has the smallest dependency set: JSON payload after `Application._load_json_body(...)`, `WorkbenchExceptionApplicationService.preview(...)`, and deterministic `404` / `400` / `200` response mapping.
- It does not involve freshness guard, auth context, request timing, request id, relation write idempotency, operation barrier, or read model refresh behavior.
- It is covered by existing API tests for exception preview and can be guarded statically without broad behavior changes.

Explicit non-goals for the next slice:

- Do not move exception apply, confirm/cancel/withdraw, cash special, bank exception, personal advance, cancel exception, ignore, or unignore in the same slice.
- Do not change response shape, status code, exception type mapping, freshness guard behavior, relation write behavior, operation barrier behavior, read model refresh behavior, or frontend API behavior.
- Do not implement Go, Go Fiber, or Go Worker.

## Seven Test Category Decision

This audit slice did not change runtime behavior.

Covered by evidence:

- API contract tests: existing `tests/test_workbench_v2_api.py` covers modern Workbench action routes, including exception preview/apply.
- Service-layer tests: existing `tests/test_workbench_write_characterization.py` covers facade-backed write behavior for the modern action family.
- Read model/cache/background job tests: existing Workbench module matrix covers freshness, operation barrier and worker behavior; no runtime read model behavior changed in this audit.
- Existing feature regression tests: static guard update records the queue transition and prevents accidental Go admission while modular IO gaps remain.

Not applicable to this audit slice:

- Business core unit tests: no business rule changed.
- Frontend component/interaction tests: no frontend behavior changed.
- End-to-end business-flow integration tests: no runtime behavior changed.

## State Machine Impact

- `MODULE-QUEUE.md` row 194 should move from `pending` to `analysis-closed`.
- Add row 195 as `server-py:workbench-exception-preview-route-owner-extraction` with `pending`.
- `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md` should point to row 195.
- Global state definitions in `03-REFACTOR-STATE-MACHINE.md` are unchanged.
- Module state definitions under `docs/modules/reconciliation-workbench/` and `docs/modules/workbench-relations/` are unchanged because this slice only records route-owner migration planning.

## Verification

Target commands for this analysis slice:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
bash scripts/verify.sh docs
git diff --check
```
