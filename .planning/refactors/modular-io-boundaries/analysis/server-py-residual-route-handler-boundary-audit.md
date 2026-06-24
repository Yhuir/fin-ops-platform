# Server.py Residual Route Handler Boundary Audit

**Date:** 2026-06-24
**Boundary:** `server-py:residual-route-handler-boundary-audit`
**Slice status:** `analysis-closed`
**Module closure:** `implementation-gap-open`

## Goal

Audit residual `server.py` route/handler/helper surfaces after prior route module work, classify ownership and risk, then select one narrow follow-up boundary.

This slice does not move, delete or rewrite runtime code.

## Evidence Reviewed

- `.planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md`
- `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
- `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
- `.planning/refactors/modular-io-boundaries/analysis/planning-post-workbench-compute-evidence-gate-next-boundary-selection.md`
- `docs/app-architecture/runtime-and-ownership.md`
- `docs/modules/README.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_*.py`
- `backend/src/fin_ops_platform/app/routes_workbench.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/workbench-relations/implementation-notes.md`

## Current Inventory

AST inventory from current `server.py`:

- Lines: `21519`
- Function definitions: `1062`
- Private functions/methods: `1031`
- `_handle_api_*` functions: `205`
- `_handle*` functions in the broader residual handler scan: `255`

Prefix counts:

| Prefix | Count |
| --- | ---: |
| `_handle_api_` | 205 |
| `_build_` | 17 |
| `_persist*` | 17 |
| `_get_` | 17 |
| `_enqueue*` | 15 |
| `_rebuild*` | 5 |
| Other private functions | 755 |
| Public functions | 31 |

Residual handler owner estimate:

| Estimated owner | Handler count |
| --- | ---: |
| `workbench` | 76 |
| `pending-invoices` | 22 |
| `no-oa-bank-batches` | 21 |
| `input-invoice-usage` | 20 |
| `output-invoice-collections` | 20 |
| `oa-pending-payments` | 16 |
| `turnover-ledger` | 16 |
| `platform/other` | 14 |
| `imports` | 12 |
| `bank-details` | 12 |
| `tax-offset` | 8 |
| `settings-health` | 7 |
| `cost-statistics` | 6 |
| `batch-accounting` | 3 |
| `etc` | 2 |

Route module construction is already partially established:

- `BankDetailsApiRoutes`
- `BatchAccountingApiRoutes`
- `CostStatisticsApiRoutes`
- `EtcBusinessBatchApiRoutes`
- `TaxApiRoutes`
- `NoOaBankBatchApiRoutes`
- `OaPendingPaymentApiRoutes`
- `OutputInvoiceCollectionApiRoutes`
- `PendingInvoiceApiRoutes`
- `TurnoverLedgerApiRoutes`
- `WorkbenchApiRoutes`

However, existing route modules do not imply their module is closed. `server.py` still contains residual HTTP dispatch, auth/error mapping, application-service assembly, legacy compatibility wrappers and some business-adjacent handlers.

## High-Risk Residual Groups

### Workbench residual handlers

Workbench is the largest residual group in the scan. Examples:

- `_handle_api_workbench_from_sql_read_model(...)`
- `_handle_api_workbench_groups(...)`
- `_handle_api_workbench_events(...)`
- `_handle_api_workbench_confirm_link(...)`
- `_handle_api_workbench_cancel_link(...)`
- `_handle_api_workbench_withdraw_link(...)`
- `_handle_api_workbench_confirm_cash_pass_through(...)`
- `_handle_api_workbench_confirm_cash_ticket_purchase(...)`
- `_handle_api_workbench_confirm_personal_advance_repayment(...)`
- `_handle_live_workbench_confirm_link(...)`
- `_handle_live_workbench_cancel_link(...)`
- `_handle_live_workbench_withdraw_link(...)`
- `_handle_workbench_confirm(...)`
- `_handle_workbench_difference(...)`
- `_handle_workbench_exception(...)`
- `_handle_workbench_offline(...)`
- `_handle_workbench_offset(...)`
- `_handle_legacy_workbench_exception_via_application(...)`

Risk:

- Multiple generations of Workbench action handlers coexist: API v2 write facade paths, live workbench wrappers, and legacy reconciliation service handlers.
- Some wrappers delegate to `WorkbenchWriteFacade`, while older handlers still call `self._reconciliation_service` and `self._ledger_service` directly.
- These are write-adjacent and audit/permission-sensitive. They are not safe to delete without caller and API-shape proof.

### Import and ETC residual handlers

Examples:

- `_handle_api_etc_import_confirm(...)`
- `_handle_api_etc_reconciliation_upload(...)`
- `_handle_import_file_confirm(...)`
- `_handle_api_etc_business_batch_delete(...)`
- `_handle_api_etc_batch_delete(...)`

Risk:

- Import confirmation touches jobs, source files, downstream read models and potentially object storage.
- ETC and import routes have route modules and services, but old compatibility flows still exist in `server.py`.

### Settings / health / runtime residuals

Examples:

- `_handle_api_session_me(...)`
- `_handle_prometheus_metrics(...)`
- `_handle_api_workbench_settings_update(...)`
- `_handle_api_workbench_settings_data_reset_job_create(...)`

Risk:

- These are platform/bootstrap or admin-sensitive boundaries.
- They often need to remain in `server.py` as HTTP/session/dependency assembly or move to dedicated platform route modules only after stronger test coverage.

## Selected Follow-Up Boundary

`server-py:workbench-legacy-action-handler-quarantine-audit`

Reason:

1. Workbench is the largest residual owner group.
2. It has existing route module coverage through `routes_workbench.py`, but that module is still thin.
3. `server.py` retains both modern write facade wrappers and older reconciliation-service action handlers.
4. The next safe step is a focused audit that classifies Workbench legacy action handlers as removed, compat-only, route-owned delegate, or blocked by caller/API evidence before any implementation slice.

Initial target functions for the next audit:

- `_handle_workbench_confirm`
- `_handle_workbench_difference`
- `_handle_workbench_exception`
- `_handle_workbench_offline`
- `_handle_workbench_offset`
- `_handle_legacy_workbench_exception_via_application`
- `_handle_live_workbench_confirm_link`
- `_handle_live_workbench_cancel_link`
- `_handle_live_workbench_withdraw_link`
- `_handle_live_workbench_mark_exception`
- `_handle_live_workbench_update_bank_exception`
- `_handle_live_workbench_oa_bank_exception`
- `_handle_live_workbench_confirm_personal_advance_repayment`
- `_handle_live_workbench_cancel_exception`
- `_handle_workbench_ignore_row_payload`
- `_handle_workbench_unignore_row_payload`

The follow-up audit should identify current route dispatch callers, tests covering each path, whether the path writes canonical facts or read-model side effects, and whether it can be removed, moved behind `WorkbenchApiRoutes`, or retained as explicitly compat-only.

## State Machine Impact

- `server-py:residual-route-handler-boundary-audit` transitions to `analysis-closed`.
- Insert `server-py:workbench-legacy-action-handler-quarantine-audit` as the next pending boundary.
- Go/Fiber/Go Worker admission remains blocked.
- Global state-machine definitions are unchanged; this is an analysis/accounting slice covered by the existing `analysis-closed` label.
- No module state-machine definitions changed.

## Seven-Category Test Applicability

| Category | Applicability | Decision |
| --- | --- | --- |
| 1. Business core unit tests | Not applicable | No business rule changed. |
| 2. Service-layer tests | Not applicable | No service behavior changed. |
| 3. API contract tests | Not applicable | No API route, shape, status or permission behavior changed. |
| 4. Read model/cache/background job tests | Not applicable | No read model, queue, cache or worker behavior changed. |
| 5. Frontend component and interaction tests | Not applicable | No frontend behavior changed. |
| 6. End-to-end business-flow integration tests | Not applicable | No runtime flow changed. |
| 7. Existing feature regression tests | Applicable | Platform guard is updated to keep the autonomous queue pointing at the selected Workbench legacy action audit and to keep Go blocked. |

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

- This slice is analysis only. It does not reduce `server.py` runtime coupling until the selected Workbench legacy action boundary is audited and then migrated or quarantined.
- The residual handler owner counts are heuristic; the follow-up audit must verify exact dispatch/caller evidence from `server.py` and tests before any deletion or migration.
- Import/ETC and read model repository shared-boundary risks remain open.
