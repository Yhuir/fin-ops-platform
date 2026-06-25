# Next Prompt

Continue after `server-py:etc-business-batch-delete-route-callback-collapse-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-business-batch-delete-route-callback-collapse-audit`.
- Row338 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-delete-route-callback-collapse-audit-2026-06-25.md`.
- `EtcBusinessBatchDeleteService` owns business-batch delete side-effect orchestration.
- `_handle_api_etc_business_batch_delete(...)` is now thin and selected for route-owner callback collapse.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-business-batch-delete-route-callback-collapse`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-business-batch-delete-route-callback-collapse-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` around:
     - `_handle_api_etc_business_batch_delete(...)`
     - `_route_api_etc_business_batch_v2(...)`
     - `_handle_api_etc_business_batches_route(...)`
     - `_handle_legacy_etc_batch_business_delete(...)`
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/services/etc_business_batch_delete_service.py`
   - relevant business batch delete tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect callers/callees for the thin delete callback and legacy fallback.
4. Implement route callback collapse:
   - extend `EtcBusinessBatchApiRoutes` with explicit delete service, JSON loader and refresh/persist ports;
   - add `delete_batch(...)` to own DELETE body parsing, service call, event execution and error/success envelope;
   - make `_route_api_etc_business_batch_v2(...)` DELETE branch authenticate mutation session and delegate to route owner;
   - keep legacy `/api/etc/batches/{id}` compatibility through an explicit resolver without side-effect ownership;
   - remove `_handle_api_etc_business_batch_delete(...)` from `server.py`.
5. Extend static Guard and run targeted delete API regressions.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change business batch delete semantics.
- Do not change reconciliation task tombstone or summary relation cancellation semantics.
- Do not pass the whole `Application` into `EtcBusinessBatchApiRoutes`.
- Do not move delete side-effect orchestration back into route code.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
