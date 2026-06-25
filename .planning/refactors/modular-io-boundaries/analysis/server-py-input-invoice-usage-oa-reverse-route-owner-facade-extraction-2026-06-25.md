# server-py:input-invoice-usage-oa-reverse-route-owner-facade-extraction

Status: `local-implementation-closed`

## Scope

This slice extracted the lightweight input-invoice usage OA reverse HTTP mapping from `Application` into an explicit route owner without changing response shape, permission behavior, idempotency behavior, read model invalidation, or OA draft mutation semantics.

Moved into `InputInvoiceUsageOaReverseApiRoutes`:

- `POST /api/input-invoice-usage/oa-reverse/preview`
- `GET /api/input-invoice-usage/oa-reverse/submitted-history`
- `GET /api/input-invoice-usage/oa-reverse/staged-drafts`
- `POST /api/input-invoice-usage/oa-reverse/batches`
- `GET /api/input-invoice-usage/oa-reverse/batches/{batch_id}`

Explicitly retained in `Application` for a follow-up boundary:

- `POST /api/input-invoice-usage/oa-reverse/oa-draft`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft/revoke`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-status/refresh`
- `POST /api/input-invoice-usage/oa-reverse/batches/{batch_id}/manual-oa-status`

Rows, filter-options, export and read model freshness gates were out of scope.

## Implementation Evidence

- Added `backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py`.
- Added `InputInvoiceUsageOaReverseApiRoutes` with explicit constructor ports:
  - `service`
  - `resolve_read_session`
  - `mutation_actor`
  - `load_json_body`
  - `json_response`
  - `input_usage_error_response`
  - `oa_reverse_error_response`
- Added `Application._input_invoice_usage_oa_reverse_routes(...)` as dependency assembly only.
- Changed OA reverse route dispatch so the route owner handles moved paths first and returns `None` for retained mutation paths.
- Removed these legacy app handlers:
  - `_handle_api_input_invoice_usage_oa_reverse_preview`
  - `_handle_api_input_invoice_usage_oa_reverse_batch_create`
  - `_handle_api_input_invoice_usage_oa_reverse_submitted_history`
  - `_handle_api_input_invoice_usage_oa_reverse_staged_drafts`
  - `_handle_api_input_invoice_usage_oa_reverse_batch_get`
- Added route-owner inventory and ownership Guard coverage in `tests/test_platform_runtime_boundary_guards.py`.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/app/routes_input_invoice_usage_oa_reverse.py backend/src/fin_ops_platform/app/server.py tests/test_platform_runtime_boundary_guards.py tests/test_input_invoice_usage_api.py
```

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_server_route_owner_inventory_stays_registered tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_oa_reverse_lightweight_routes_use_route_owner tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_input_invoice_oa_reverse_relation_writer_uses_command_boundary -v
```

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_preview_batch_and_missing_client_draft_routes_are_formal_workflow tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_preview_marks_candidate_oa_relation_as_non_selectable tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_draft_route_creates_draft_then_waits_for_user_submission_confirmation tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_one_step_draft_route_uses_target_applicant_provider tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_staged_drafts_route_returns_created_drafts_for_recovery tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_full_flow_uses_admin_saved_target_applicant_credential tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_one_step_draft_route_returns_missing_credential_error tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_not_submitted_api_flow_returns_to_create_ready_and_recreates tests.test_input_invoice_usage_api.InputInvoiceUsageApiTests.test_oa_reverse_status_refresh_returns_relation_command_conflict_without_saving_detected_batch -v
```

## Docs Impact

`docs/modules/input-invoice-usage/implementation-notes.md` was updated because route ownership for the OA reverse workflow changed.

## Remaining Risk

Local behavior is protected by API regression and static Guard evidence. Production browser/admin/write evidence remains a final validation gate and was intentionally not run in this local implementation slice.

## Next Boundary

`server-py:input-invoice-usage-oa-reverse-draft-mutation-callback-audit`

Audit the remaining OA reverse draft mutation callbacks before any migration because they include OA client/provider integration, version/idempotency checks, relation command writes, manual status decisions and status refresh behavior.
