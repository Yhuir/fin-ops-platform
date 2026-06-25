# server-py:etc-legacy-batch-read-facade-extraction

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:etc-legacy-batch-read-payload-facade-audit`
**Next boundary:** `server-py:etc-legacy-batch-route-callback-collapse-audit`

## Goal

Extract legacy `/api/etc/batches` list/detail/count/filter payload composition from `Application` into an explicit read facade without changing the public response shape.

No production browser, admin or controlled-write validation was run.

## Implementation

Added:

- `backend/src/fin_ops_platform/services/etc_legacy_batch_read_facade.py`
  - `EtcLegacyBatchReadFacade`
  - `list_payload(...)`
  - `detail_payload(...)`
  - internal unified business/submission/import list/detail/count/filter helpers

Updated:

- `backend/src/fin_ops_platform/app/server.py`
  - imports and constructs `EtcLegacyBatchReadFacade`;
  - delegates `_handle_api_etc_batches(...)` list payload composition;
  - delegates `_handle_api_etc_batch_detail(...)`;
  - uses facade detail payload for draft-for-batch validation;
  - removes legacy read payload helper ownership from `Application`.

Tests:

- `tests/test_etc_legacy_batch_read_facade.py`
  - covers counts, selected detail, top-level invoice items and keyword filtering;
  - covers unknown detail returning `None`.
- `tests/test_platform_runtime_boundary_guards.py`
  - guards that legacy read payload composition uses the facade;
  - guards removed `Application` read helper definitions;
  - guards facade against app/auth/server imports and HTTP response construction.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_legacy_batch_read_facade.py backend/src/fin_ops_platform/app/server.py tests/test_etc_legacy_batch_read_facade.py tests/test_platform_runtime_boundary_guards.py
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_legacy_batch_read_facade -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_read_payload_uses_facade_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_lifecycle_side_effects_use_service_boundary tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_delete_side_effects_use_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_etc_batch_query_api_returns_counts_summary_plate_summary_and_items tests.test_etc_backend.EtcApiTests.test_etc_batch_list_only_checks_attachment_status_for_selected_detail tests.test_etc_backend.EtcApiTests.test_reconciliation_backed_submitted_batch_detail_includes_supplement_metadata tests.test_etc_backend.EtcApiTests.test_reconciliation_import_batch_route_creates_oa_draft -v
bash scripts/verify.sh docs
git diff --check
```

## Seven Test Categories

- Business core unit tests: covered through facade tests for counts/filter/detail payload behavior.
- Service-layer tests: covered by `tests/test_etc_legacy_batch_read_facade.py`.
- API contract tests: covered by targeted legacy list/detail/query API regressions.
- Read model/cache/background job tests: not directly applicable; this slice changes local payload ownership, not read model/job behavior.
- Frontend component/interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: partially covered by existing backend import -> draft/list/detail flows.
- Existing feature regression tests: covered by legacy query/list/detail/supplement metadata regressions and static boundary guard.

## Docs Impact

Updated ETC module implementation notes and modular IO autonomous state. Product/API/operations docs were not changed because public behavior did not change.

## Remaining Risk

- `EtcLegacyBatchApiRoutes` still receives callbacks for list/detail/delete/draft/confirm/reopen instead of owning those HTTP handlers directly.
- Business-batch v2 behavior remained intentionally out of scope.
- Local modular implementation closure remains unproven across the whole repository.
- Production browser/admin/write validation remains final validation only and was not run.
