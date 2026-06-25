# server-py:etc-legacy-batch-delete-side-effect-service-audit

**Date:** 2026-06-25
**Status:** local-implementation-closed
**Previous boundary:** `server-py:etc-legacy-batch-route-owner-audit`
**Next boundary:** `server-py:etc-legacy-batch-draft-confirm-callback-audit`

## Goal

Move legacy `/api/etc/batches/{batch_id}` DELETE business side effects out of `Application` without changing the legacy HTTP response contract or business-batch v2 delete behavior.

This slice is local-first only. No production browser, admin or controlled-write validation was run.

## Evidence Read

- `.planning/refactors/modular-io-boundaries/autonomous/NEXT-PROMPT.md`
- `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-route-owner-audit-2026-06-25.md`
- `backend/src/fin_ops_platform/app/server.py`
- `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
- `backend/src/fin_ops_platform/services/etc_reconciliation_import_cleanup_service.py`
- `tests/test_etc_backend.py`
- `tests/test_platform_runtime_boundary_guards.py`
- `docs/modules/etc-tickets/implementation-notes.md`

CodeGraph was used to inspect the legacy batch route owner, `Application._handle_api_etc_batch_delete`, cleanup service relationships and existing ETC services before implementation.

## Decision

The next safe boundary was not a route-owner migration. The route owner already owns URL parsing, but the DELETE callback still mixed:

- submission/import batch discovery;
- task link repair;
- imported invoice canonical cleanup;
- import source cleanup;
- OA draft deleted task transition;
- refresh reason selection;
- persistence sequencing;
- HTTP error mapping.

Moving this directly into `EtcLegacyBatchApiRoutes` would make a route owner own business side effects. Instead, this slice introduced `EtcLegacyBatchDeleteService` as a service boundary:

- Service owns non-business legacy batch delete side effects.
- Service receives explicit dependencies only.
- Service does not receive `Application`.
- Service does not import app/auth/server modules.
- Service does not construct HTTP responses.
- Service returns `EtcLegacyBatchDeleteResult` with `refresh_events`.
- `Application` keeps business-batch v2 fallback, HTTP status mapping, `_refresh_after_etc_invoice_link(...)` and `_persist_state()` mapping.

Business-batch v2 delete remains intentionally unchanged in this slice.

## Implementation

Added:

- `backend/src/fin_ops_platform/services/etc_legacy_batch_delete_service.py`
  - `EtcLegacyBatchDeleteService`
  - `EtcLegacyBatchDeleteResult`
  - `EtcLegacyBatchRefreshEvent`

Updated:

- `backend/src/fin_ops_platform/app/server.py`
  - imports `EtcLegacyBatchDeleteService`;
  - adds `_etc_legacy_batch_delete_service()`;
  - reduces `_handle_api_etc_batch_delete(...)` to:
    - business-batch legacy fallback;
    - service call for non-business delete;
    - refresh/persist event application;
    - HTTP error/response mapping.

Tests:

- `tests/test_etc_legacy_batch_delete_service.py`
  - covers missing submission batch repair returning refresh/persist event and import cleanup;
  - covers import batch delete returning refresh/persist event without HTTP/Application dependency.
- `tests/test_platform_runtime_boundary_guards.py`
  - guards that legacy batch delete side effects delegate to service;
  - guards that the service does not import app/server/auth or construct response details.

## Verification

Passed:

```bash
PYTHONPATH=backend/src python3 -m py_compile backend/src/fin_ops_platform/services/etc_legacy_batch_delete_service.py backend/src/fin_ops_platform/app/server.py
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_legacy_batch_delete_service -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_etc_legacy_batch_delete_side_effects_use_service_boundary -v
PYTHONPATH=backend/src python3 -m unittest tests.test_etc_backend.EtcApiTests.test_delete_etc_batch_route_deletes_unsubmitted_and_submitted tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_cascades_mutable_batch_contents tests.test_etc_backend.EtcApiTests.test_delete_etc_submission_batch_route_repairs_stale_invoice_references tests.test_etc_backend.EtcApiTests.test_unsubmitted_oa_draft_batch_is_listed_and_deletable tests.test_etc_backend.EtcApiTests.test_delete_missing_unsubmitted_oa_draft_batch_repairs_reconciliation_task_link -v
```

Broader docs/diff checks are recorded in the controller commit for this slice.

## Seven Test Categories

- Business core unit tests: covered through direct service tests for delete/repair state transitions and cleanup side effects.
- Service-layer tests: covered by `tests/test_etc_legacy_batch_delete_service.py`.
- API contract tests: covered by targeted legacy batch DELETE API regressions in `tests/test_etc_backend.py`.
- Read model/cache/background job tests: not directly applicable; this slice preserved existing refresh event reasons and did not add a read model/job contract.
- Frontend component/interaction tests: not applicable; no frontend behavior changed.
- End-to-end business-flow integration tests: partially covered by existing backend API flows for import -> draft -> delete/repair.
- Existing feature regression tests: covered by targeted legacy batch delete/draft repair regressions and static boundary guard.

## Docs Impact

Updated ETC module implementation notes and modular IO autonomous state. Product, API and operation docs were not changed because the public contract and production operation model did not change.

## Remaining Risk

- Legacy batch draft/create/confirm/mark-not-submitted callbacks still remain in `Application` as explicit callbacks behind `EtcLegacyBatchApiRoutes`.
- Business-batch v2 delete still has substantial side-effect orchestration in `Application`; it was intentionally out of scope for this slice.
- Production browser/admin/write validation remains final validation only and was not run.
