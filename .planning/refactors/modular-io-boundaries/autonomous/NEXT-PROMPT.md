# Next Prompt

Continue after `server-py:etc-legacy-batch-read-payload-facade-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-legacy-batch-read-payload-facade-audit`.
- Row319 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-read-payload-facade-audit-2026-06-25.md`.
- Row318 implementation added `EtcLegacyBatchLifecycleService`.
- Row317 implementation added `EtcLegacyBatchDeleteService`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-legacy-batch-read-facade-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-read-payload-facade-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` legacy batch list/detail/payload helper sections
   - `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
   - `docs/modules/etc-tickets/implementation-notes.md`
   - `tests/test_platform_runtime_boundary_guards.py`
   - targeted ETC legacy list/detail/query tests in `tests/test_etc_backend.py`
3. Use CodeGraph to inspect `_handle_api_etc_batches`, `_handle_api_etc_batch_detail`, `_etc_batch_list_items`, `_etc_batch_detail_payload`, `_etc_batch_counts`, `_etc_batch_summary_matches_filters`, `_etc_batch_detail_filtered_for_query` and helper callers.
4. Extract a focused `EtcLegacyBatchReadFacade` only if the helper ownership can move without changing response semantics.
5. Add facade/service tests and static guard coverage.
6. Update state machine and module implementation notes.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not do broad `server.py` line-count splitting.
- Do not duplicate existing route owners, services or repositories.
- Do not change business/API response semantics without explicit tests.
- Do not pass the whole `Application` into route owners or services.
- Do not change business-batch v2 route behavior in this slice.
- Preserve unified business/submission/import list semantics, submitted/unsubmitted counts, reconciliation import exclusion, attachment-status checks, detail filtering and supplement metadata.
