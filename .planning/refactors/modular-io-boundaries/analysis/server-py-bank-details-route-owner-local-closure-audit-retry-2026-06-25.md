# server-py:bank-details-route-owner-local-closure-audit-retry

**Date:** 2026-06-25
**Status:** analysis-closed
**Module closure:** implementation-gap-open

## Scope

Re-audit bank-details route ownership after `PATCH /api/bank-details/transactions/categories` moved into `BankDetailsApiRoutes.route(...)`.

This was an analysis-only slice. It did not change runtime code, API behavior, read models, workers, frontend code or production data.

## Evidence

`server.py` no longer owns bank-details route callbacks:

- No `_handle_api_bank_details*` methods remain.
- No `_handle_api_bank_detail_category*` methods remain.
- No `_handle_api_bank_transaction_categories(...)` method remains.
- `/api/bank-details/...` dispatch is a single delegate:
  - `self._bank_details_routes().route(method, route_path, query, body, headers)`

`routes_bank_details.py` owns the bank-details HTTP mapping surface:

- `GET /api/bank-details/auto-tag-rules`
- `PUT /api/bank-details/auto-tag-rules`
- `POST /api/bank-details/auto-tag-rules/reapply`
- `POST /api/bank-details/auto-tag-rules/file-replacement`
- `PATCH /api/bank-details/transactions/categories` as disabled `410 Gone`
- `GET /api/bank-details/accounts`
- `GET /api/bank-details/transactions`
- `GET /api/bank-details/transactions/export`
- `POST` / `DELETE` category assignment and confirmation subroutes

Remaining bank-related `Application` methods are not bank-details route callbacks. They classify as:

- composition root / dependency assembly:
  - `_bank_details_application_service(...)`
  - `_bank_details_routes(...)`
- HTTP/platform adapters:
  - `_resolve_bank_details_read_session(...)`
  - `_bank_details_export_response(...)`
  - `_load_json_body(...)` injected into the route owner
- read-model/source-version/refresh/provider ports:
  - `_bank_detail_read_model_refresh_producer(...)`
  - `_bank_account_balance_read_model_refresh_producer(...)`
  - `_bank_detail_available_month_scope_provider(...)`
  - `_bank_transaction_category_affected_months(...)`
  - `_invalidate_workbench_after_bank_transaction_categories(...)`
- shared upstream/downstream support for other modules:
  - bank transaction tag reader/facade helpers used by turnover ledger, no-OA bank batch, workbench and import flows

## Conclusion

Bank-details `server.py` route-owner local support is accounted for: no app-owned bank-details route callback remains.

This does not mean bank-details module/global closure:

- broader bank details read-model/runtime evidence remains production-deferred;
- real PostgreSQL/worker/App Status/browser/admin/write evidence remains unavailable in the current local environment;
- `server.py` still has app-owned route callbacks for other modules.

## Next Boundary Selection

Selected next local-first boundary:

`server-py:no-oa-bank-batch-route-owner-audit`

Reason:

- `server.py` still contains multiple `_handle_api_no_oa_bank_batch*` callbacks.
- `NoOaBankBatchApiRoutes` and `NoOaBankBatchApplicationService` already exist, so a bounded audit can classify thin HTTP wrappers versus side-effect/service extraction needs.
- This keeps production validation deferred while local modular code gaps remain.

## Verification

Passed:

- `rg -n "def _handle_api_bank|_handle_api_bank_details|_handle_api_bank_detail_category|_handle_api_bank_transaction_categories|/api/bank-details" backend/src/fin_ops_platform/app/server.py backend/src/fin_ops_platform/app/routes_bank_details.py`
- `rg -n "def _.*bank_detail|def _.*bank_details|def _.*bank_transaction|def _bank_" backend/src/fin_ops_platform/app/server.py`
- CodeGraph context for bank-details route ownership and application service boundary
- `bash scripts/verify.sh docs`
- `git diff --check`

## Remaining Risk

- No production validation, browser smoke, admin auth evidence or controlled write apply was executed.
- No module/global closure is claimed.
- Next module audit must be bounded to no-OA bank batch route ownership and must not migrate broad side effects into route code.
