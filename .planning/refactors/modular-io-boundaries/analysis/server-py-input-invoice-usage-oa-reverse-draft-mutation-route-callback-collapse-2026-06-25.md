# server-py:input-invoice-usage-oa-reverse-draft-mutation-route-callback-collapse

Status: `local-implementation-closed`

## Scope

This slice collapsed the remaining input-invoice usage OA reverse mutation HTTP callbacks from `Application` into `InputInvoiceUsageOaReverseApiRoutes`.

Moved into the route owner:

- `POST /api/input-invoice-usage/oa-reverse/oa-draft`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft/revoke`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-status/refresh`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/manual-oa-status`

Rows, filter-options, export and read model freshness gates were not changed.

## Implementation Evidence

- Extended `InputInvoiceUsageOaReverseApiRoutes.route(...)` to handle the remaining mutation paths.
- Added explicit route-owner ports:
  - `target_oa_applicant_token_provider`
  - `oa_draft_client_for_batch`
  - `int_or_none`
- Removed these legacy app handlers:
  - `_handle_api_input_invoice_usage_oa_reverse_one_step_draft_create`
  - `_handle_api_input_invoice_usage_oa_reverse_draft_create`
  - `_handle_api_input_invoice_usage_oa_reverse_draft_revoke`
  - `_handle_api_input_invoice_usage_oa_reverse_status_refresh`
  - `_handle_api_input_invoice_usage_oa_reverse_manual_status`
- Kept `Application` responsible for dependency assembly and platform helper ports only.
- Extended the platform route-owner Guard so all OA reverse HTTP mapping now belongs to `InputInvoiceUsageOaReverseApiRoutes`.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_input_invoice_usage_api.py
```

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_oa_reverse_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_oa_reverse_relation_writer_uses_command_boundary -v
```

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_preview_batch_and_missing_client_draft_routes_are_formal_workflow tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_preview_marks_candidate_oa_relation_as_non_selectable tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_draft_route_creates_draft_then_waits_for_user_submission_confirmation tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_one_step_draft_route_uses_target_applicant_provider tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_staged_drafts_route_returns_created_drafts_for_recovery tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_full_flow_uses_admin_saved_target_applicant_credential tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_one_step_draft_route_returns_missing_credential_error tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_not_submitted_api_flow_returns_to_create_ready_and_recreates tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_status_refresh_returns_relation_command_conflict_without_saving_detected_batch -v
```

## Docs Impact

`docs/modules/input-invoice-usage/implementation-notes.md` was updated because OA reverse route ownership changed again.

## Remaining Risk

Local behavior is protected by API regression and static Guard evidence. Real OA login, target applicant credential behavior in production, browser/admin/write evidence and worker/App Status drain evidence remain final validation gates and were intentionally not run in this local implementation slice.

## Next Boundary

`server-py:input-invoice-usage-oa-reverse-route-owner-local-closure-audit`

Audit whether all OA reverse route-owner responsibilities are now locally accounted for, and classify any remaining `Application` helpers as platform/dependency assembly, explicit ports, or implementation gaps.
