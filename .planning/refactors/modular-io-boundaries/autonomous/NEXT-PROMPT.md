# Next Prompt

Continue after `server-py:etc-legacy-batch-read-facade-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-legacy-batch-read-facade-extraction`.
- Row320 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-read-facade-extraction-2026-06-25.md`.
- Row320 implementation added `EtcLegacyBatchReadFacade` and moved legacy batch list/detail/count/filter payload composition out of `Application`.
- Row318/317 already moved lifecycle and delete side effects into services.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-legacy-batch-route-callback-collapse-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-read-facade-extraction-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
   - `backend/src/fin_ops_platform/app/server.py` `_etc_legacy_batch_routes` and remaining legacy batch callbacks
   - `backend/src/fin_ops_platform/services/etc_legacy_batch_read_facade.py`
   - `backend/src/fin_ops_platform/services/etc_legacy_batch_delete_service.py`
   - `backend/src/fin_ops_platform/services/etc_legacy_batch_lifecycle_service.py`
   - `tests/test_platform_runtime_boundary_guards.py`
   - targeted ETC legacy route tests in `tests/test_etc_backend.py`
3. Use CodeGraph to inspect the remaining callback ownership between `EtcLegacyBatchApiRoutes` and `Application`.
4. Decide whether the next safe implementation is:
   - moving all legacy batch HTTP handlers into `EtcLegacyBatchApiRoutes` with explicit ports;
   - extracting a business-batch legacy delete fallback port first;
   - or closing a narrower callback group.
5. Update analysis/state and add tests for any accepted implementation.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not pass `Application` into route owners or services.
- Do not change business-batch v2 behavior without explicit tests.
- Do not hide business-batch delete fallback semantics behind an untyped callback without documenting owner/deletion condition.
