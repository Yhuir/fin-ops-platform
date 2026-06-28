# Read Model Main Write Target Inventory

Date: 2026-06-26
Branch: `main`
Scope: `main-read-model-closure:wave-1-static-guard-and-write-target-inventory`

This inventory is source-backed by route method scans in `backend/src/fin_ops_platform/app/routes*.py`, keyword scans for `affected_months`, `affected_scopes`, `read_model_status`, `operation_barrier`, `freshness_targets`, `dirty`, `outbox`, and module boundary docs under `docs/modules/*/boundary-io.md`.

No production mutation, queue mutation, readiness mutation, force refresh, repair, DB write, or mutating HTTP sample was run for this wave.

## Findings

- Current backend route owners expose many business write methods, but only a small subset add explicit route-level affected target fields.
- Existing response targets are inconsistent: `routes_batch_accounting.py` returns `affected_months`; `routes_no_oa_bank_batches.py` aggregates `affected_months`; `routes_etc_import.py` has an `affected_scopes` audit/logging style marker. Most other page write routes delegate to service results without route-level freshness target normalization.
- No route keyword scan found a consistent response field named `freshness_targets`, `operation_barrier_targets`, `read_model_targets`, or equivalent across all page write APIs.
- Several modules may already return useful targets from service-level results, but that is not yet a page/API-wide contract. Wave 2 must standardize the response contract and tests at the boundary where writes leave the backend.
- Frontend production code currently contains classified default-`fresh` fallbacks. Wave 2 must remove or hard-quarantine them so missing/unknown status cannot be rendered as final fresh data.
- Legacy reachability is already partially guarded in `tests/test_platform_runtime_boundary_guards.py`; this inventory marks the remaining old-path surfaces that must be deleted or hard-quarantined before closure.

## Write Operation Matrix

| Module | Route/API source | Business writes | Affected read models/scopes | Current response target evidence | Closure status | Restore strategy |
| --- | --- | --- | --- | --- | --- | --- |
| `workbench` | `backend/src/fin_ops_platform/app/routes_workbench_actions.py`; compat `routes_workbench.py`; legacy quarantine `routes_legacy_workbench_actions.py` | `exception_apply`, `confirm_link`, `mark_exception`, `cancel_link`, `withdraw_link`, `confirm_cash_pass_through`, `confirm_cash_ticket_purchase`, `cancel_cash_special`, `update_bank_exception`, `oa_bank_exception`, `confirm_personal_advance_repayment`, `cancel_exception`, `ignore_row`, `unignore_row` | `workbench`, `workbench_relation`, and downstream page scopes derived from relation/action type | Route owner delegates to write facade/service result. Route-level scan did not find standardized `freshness_targets` or `operation_barrier_targets`. | Needs response target normalization and frontend barrier proof. Legacy action route must remain compat-only until deletion proof. | business inverse for confirm/cancel/withdraw where available; bounded DB restore only for selected production validation samples without business inverse. |
| `batch-accounting` | `backend/src/fin_ops_platform/app/routes_batch_accounting.py` | `submit`, `withdraw` | `workbench_relation` and downstream scopes from changed row ids/month scope | Route response adds `affected_months` for both submit and withdraw. No standard freshness/barrier target field yet. | Partial target evidence; needs standard read model target envelope and frontend wait/fresh reload proof. | business inverse via `withdraw` after `submit`; bounded DB restore fallback only if a selected sample lacks a valid inverse. |
| `bank-details` | `backend/src/fin_ops_platform/app/routes_bank_details.py` | `update_auto_tag_rules`, `replace_auto_tag_rules_from_file_source`, `reapply_auto_tag_rules`, `confirm_category`, `revoke_category_confirmation`, `assign_category`, `clear_category_assignment` | `bank_detail`; `bank_account_balance` for derived balance changes; downstream `workbench_relation`, `no_oa_bank_batch`, `turnover_ledger` where labels drive relation display or scoped projections | Route-level scan only found read `read_model_status` handling. Write methods return application service payloads without standardized route-level target fields. | Needs service result audit, standard target envelope, and frontend write-after-refresh barrier. | business inverse for category confirmation/assignment where exposed; bounded DB restore fallback for sample-only state recovery. |
| `bank-account-balance` | Indirect through `routes_bank_details.py`, import/lifecycle, and worker refresh | No standalone page mutation; balance changes are induced by bank import, bank detail lifecycle, or repair/backfill | `bank_account_balance:all` all-only scope | No direct page write response. Non-applicability must be explicit: upstream writers should include `bank_account_balance:all` when balance freshness is affected. | Needs indirect target contract from bank import/bank detail lifecycle and App Status proof. | upstream sample restored through business inverse or bounded DB restore according to the originating operation. |
| `pending-invoices` | `backend/src/fin_ops_platform/app/routes_pending_invoices.py` | `attach_existing_confirm`, `attach_existing_batch_confirm`, `update_rules`, `update_income_status`, `update_income_statuses` | `pending_invoice` direction/filter/month scopes, `invoice_lifecycle`, `search`, `workbench_relation` depending on operation | Read routes expose `read_model_status`; write methods delegate to application/rules services. Route-level scan did not find standardized freshness/barrier target fields. | Needs write response targets and frontend wait/refetch closure. | business inverse for relation/status changes where supported; bounded DB restore fallback for validation sample restoration only. |
| `input-invoice-usage` | `backend/src/fin_ops_platform/app/routes_input_invoice_usage.py`; `routes_input_invoice_usage_oa_reverse.py` | `update_payment_status_rules`, `create_batch`, `create_oa_draft_from_selection`, `create_oa_draft`, `revoke_oa_draft`, `refresh_oa_status`, `manual_oa_status` | `input_invoice_usage`, `invoice_lifecycle`, `search`, OA-related scopes | Read routes expose `read_model_status`; write methods return service payloads without a consistent route-level target envelope. | Needs target normalization and OA reverse write closure proof. | business inverse for OA draft revoke where available; bounded DB restore fallback for selected sample-only recovery. |
| `oa-pending-payments` | `backend/src/fin_ops_platform/app/routes_oa_pending_payments.py` | `confirm_paid`, `link_bank_transactions`, `auto_reconcile_bank_transactions` | `oa_pending_payment`, `bank_detail`, `workbench_relation`, `invoice_lifecycle/search` when relations or status change | Read/detail status uses `_read_model_status_code`; write route returns command service result. Route-level scan did not find standardized freshness/barrier target fields. | Needs command response target contract, operation barrier targets, and production sample restore proof. | business inverse if command exposes reversal; bounded DB restore fallback if selected sample has no business inverse. |
| `output-invoice-collections` | `backend/src/fin_ops_platform/app/routes_output_invoice_collections.py` | `set_collection_status`, `upsert_collection_reminder`, `cancel_collection_reminder`, `confirm_red_invoice_relation`, `revoke_red_invoice_relation`, `create_receipt`, `void_receipt`, `reissue_receipt`, `update_receipt_settings` | `output_invoice_collection`, `invoice_lifecycle`, `search`, possible `workbench_relation`/receipt related scopes | Read routes expose freshness; write methods delegate to services. No consistent route-level `freshness_targets` or barrier targets found in keyword scan. | Needs write target envelope and frontend mutation fresh reload proof. | business inverse for revoke/void/cancel where exposed; bounded DB restore fallback for selected sample-only recovery. |
| `cost-statistics` | `backend/src/fin_ops_platform/app/routes_cost_statistics.py`; tax/cost shared lifecycle | Settings/save/import operations that affect cost-statistics source facts or parent aggregates | `cost_statistics` month shards and queryable parent aggregate | Read routes expose `read_model_status`. No direct standardized write target envelope found in cost route scan. | Needs mapping from source writes to `cost_statistics` shard/parent targets and query-plan evidence. | business inverse where source operation supports it; bounded DB restore fallback only for selected validation sample restoration. |
| `tax-offset` | `backend/src/fin_ops_platform/app/routes_tax.py` | `handle_save_plan`, certified import confirmation, calculation/apply flows | `tax_offset` month scopes and cost-tax auxiliary worker scopes | Route scan shows read status handling. Write/save/import routes do not expose a standardized target envelope at route level. | Needs save/import target envelope, barrier targets, and frontend wait/fresh reload proof. | business inverse for saved plan/import where available; bounded DB restore fallback for sample-only restoration. |
| `no-oa-bank-batches` | `backend/src/fin_ops_platform/app/routes_no_oa_bank_batches.py` | `update_tag_selection`, `submit_batch`, `withdraw_batch`, `submit_selection`, `bulk_submit` | `no_oa_bank_batch`, `workbench_relation`, `bank_detail`, downstream turnover/workbench scopes depending on selected rows | Route aggregates `affected_months` from service results and returns it. No standard freshness/barrier target envelope yet. | Partial target evidence; needs operation barrier contract and production submit/withdraw sample proof. | business inverse via withdraw where valid; bounded DB restore fallback for samples without inverse. |
| `turnover-ledger` | `backend/src/fin_ops_platform/app/routes_turnover_ledger.py` | `handle_tag_selection_update_route`, `handle_relation_extra_update_route`, `handle_confirm_relation_route`, `handle_closure_confirm_route`, `handle_closure_withdraw_route`, `handle_withdraw_relation_route`, `handle_bank_row_tags_batch_route` | `turnover_ledger`, `workbench_relation`, `bank_detail`; closure/withdraw affects month/entity scopes | Write routes return facade/UoW results. Route-level scan did not find standardized `freshness_targets`, `affected_scopes`, or barrier targets. | Needs response target normalization, frontend barrier proof, and legacy write adapter deletion/quarantine proof. | business inverse for withdraw/closure withdraw where valid; bounded DB restore fallback for selected production sample-only restoration. |
| `imports-oa-driven` | `routes_etc_import.py`, `routes_etc.py`, `routes_etc_invoices.py`, `routes_etc_reconciliation.py`, `routes_input_invoice_usage_oa_reverse.py`, import endpoints in `server.py`, OA integration services | import confirm, create/delete/revoke/manual OA status, reconciliation task create/delete/confirm/reopen, source upload/delete, invoice revoke, OA status refresh/manual override | `workbench`, `workbench_relation`, `invoice_lifecycle`, `pending_invoice`, `input_invoice_usage`, `output_invoice_collection`, `oa_pending_payment`, `search`, `bank_detail` depending on source | `routes_etc_import.py` contains `affected_scopes=["etc_invoices", "imports", "workbench"]`; other route owners generally delegate to services without a uniform target envelope. | Needs import/OA target fan-out contract and worker/readiness proof; legacy ETC batch routes remain compat-only. | business inverse for revoke/delete/reopen where exposed; bounded DB restore fallback for selected sample-only restoration. |

## Current Default-Fresh Frontend Surfaces

The guard `test_frontend_read_model_status_default_fresh_sites_are_classified` now classifies the current production frontend default-fresh sites. These are not closure-complete; they are explicit Wave 2 deletion/hard-quarantine targets:

- `web/src/features/batchAccounting/api.ts`
- `web/src/features/pendingInvoices/api.ts`
- `web/src/features/turnoverLedger/api.ts`
- `web/src/features/workbench/api.ts`
- `web/src/pages/BatchAccountingPage.tsx`
- `web/src/pages/NoOaBankBatchPage.tsx`
- `web/src/pages/OaPendingPaymentsPage.tsx`
- `web/src/pages/ReconciliationWorkbenchPage.tsx`
- `web/src/pages/TurnoverLedgerPage.tsx`

## Legacy Pollution Surfaces For Later Waves

These surfaces are still relevant to the expanded closure objective and must either be deleted or hard-quarantined with normal production reachability proof:

- `backend/src/fin_ops_platform/app/routes_legacy_workbench_actions.py`
- `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
- `backend/src/fin_ops_platform/services/turnover_ledger_write_adapters.py`
- Workbench legacy SQL/read fallback and stale payload fallback helpers in `server.py` and the extracted Workbench compatibility providers.
- Frontend missing/unknown read model status defaulting to `fresh`.

Existing architecture guards already cover parts of this quarantine. Later implementation waves must strengthen those guards as old paths are deleted or as deletion conditions become precise.

## Wave 2 Target

Converge write API responses and frontend mutation handling in one high-efficiency pass:

- Define a shared response target shape for page writes that affect read models: affected scopes, freshness targets, operation barrier targets, job/version, or explicit non-applicability.
- Add API contract tests for representative write operations in each module family.
- Remove frontend default-`fresh` fallbacks, replacing them with loading/refreshing/unknown fail-closed states.
- Prove frontend mutations wait for operation barrier or fresh reload before rendering final fresh state.
- Preserve sample restoration policy: use business inverse first; use bounded DB restore only for selected production validation samples that cannot be restored through business logic.
