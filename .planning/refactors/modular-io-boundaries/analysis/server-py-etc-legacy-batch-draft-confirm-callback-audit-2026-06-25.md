# server-py:etc-legacy-batch-draft-confirm-callback-audit

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:etc-legacy-batch-delete-side-effect-service-audit`
**Next boundary:** `server-py:etc-legacy-batch-read-payload-facade-audit`

## Goal

Audit the remaining legacy `/api/etc/batches*` draft/create/confirm/mark-not-submitted callbacks in `Application` and move the safe business lifecycle side effects into an explicit service boundary.

This slice is local-first only. No production browser, admin or controlled-write validation was run.

## Evidence Read

- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-delete-side-effect-service-audit-2026-06-25.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/etc-tickets/implementation-notes.md`

CodeGraph was used to inspect the route owner callback shape and legacy lifecycle methods before implementation.

## Decision

The safest slice was not to move all legacy callbacks into the route owner at once. Draft creation still needs HTTP body parsing and OA token/header mapping, while draft-for-batch still depends on the legacy batch detail payload. Those HTTP/read payload concerns remain in `Application` for now.

The business side effects are now service-owned:

- OA draft creation from invoice ids;
- reconciliation task `record_oa_draft_created`;
- submitted confirmation;
- reconciliation task `record_oa_submitted_confirmed`;
- mark-not-submitted/reopen;
- invoice relinking and refresh reason selection.

`Application` still owns:

- HTTP body validation;
- batch detail validation for `/api/etc/batches/{batch_id}/draft`;
- OA client construction from headers;
- HTTP error/status mapping;
- applying refresh events to `_refresh_after_etc_invoice_link(...)`.

## Implementation

Added:

- `backend/src/fin_ops_platform/services/etc_legacy_batch_lifecycle_service.py`
  - `EtcLegacyBatchLifecycleService`
  - `EtcLegacyBatchDraftResult`
  - `EtcLegacyBatchTransitionResult`
  - `EtcLegacyBatchLifecycleRefreshEvent`

Updated:

- `backend/src/fin_ops_platform/app/server.py`
  - adds `_etc_legacy_batch_lifecycle_service()`;
  - delegates `_create_etc_batch_draft_from_invoice_ids(...)`;
  - delegates `_handle_api_etc_batch_confirm_submitted(...)`;
  - delegates `_handle_api_etc_batch_mark_not_submitted(...)`.

Tests:

- `tests/test_etc_legacy_batch_lifecycle_service.py`
  - covers OA draft creation, task record and refresh event;
  - covers confirm/reopen refresh reason and task transition behavior.
- `tests/test_platform_runtime_boundary_guards.py`
  - guards lifecycle handlers against direct `create_oa_draft`, `confirm_submitted`, `mark_not_submitted` and task record calls;
  - guards service against app/auth/server imports and HTTP response construction.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_legacy_batch_lifecycle_service.py backend/src/fin_ops_platform/app/server.py tests/test_etc_legacy_batch_lifecycle_service.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_legacy_batch_lifecycle_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_delete_side_effects_use_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_lifecycle_side_effects_use_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_reconciliation_import_batch_route_creates_oa_draft tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_oa_draft_uploads_supplements_and_uses_oa_total tests.test_etc_backend.EtcApiTests.test_confirming_reconciliation_backed_oa_submission_finalizes_task tests.test_etc_backend.EtcApiTests.test_api_returns_clear_errors_for_invalid_input tests.test_etc_backend.EtcApiTests.test_unsubmitted_oa_draft_batch_is_listed_and_deletable -v
```

Broader docs/diff checks are recorded in the controller commit for this slice.

## Seven Test Categories

- Business core unit tests: covered through direct lifecycle service tests for OA draft creation, submitted confirmation and reopen transition.
- Service-layer tests: covered by `tests/test_etc_legacy_batch_lifecycle_service.py`.
- API contract tests: covered by targeted legacy draft/confirm API regressions in `tests/test_etc_backend.py`.
- Read model/cache/background job tests: not directly applicable; this slice preserved existing refresh event reasons and did not add read model/job behavior.
- Frontend component/interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: partially covered by existing backend API flows for import -> draft -> confirm and task finalization.
- Existing feature regression tests: covered by targeted legacy API regressions and static boundary guard.

## Docs Impact

Updated ETC module implementation notes and modular IO autonomous state. Product, API and operation docs were not changed because public behavior did not change.

## Remaining Risk

- Legacy batch list/detail payload and batch-detail validation remain in `Application`.
- Route owner still receives explicit callbacks for list/detail/draft/confirm/reopen; the next boundary should audit read payload ownership before removing more callbacks.
- Business-batch v2 behavior remained intentionally out of scope.
- Production browser/admin/write validation remains final validation only and was not run.
