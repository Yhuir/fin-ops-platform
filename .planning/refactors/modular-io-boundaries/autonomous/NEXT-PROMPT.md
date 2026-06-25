# Next Prompt

Continue after `server-py:etc-legacy-batch-draft-confirm-callback-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-legacy-batch-draft-confirm-callback-audit`.
- Row318 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-draft-confirm-callback-audit-2026-06-25.md`.
- Prior delete service boundary: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-delete-side-effect-service-audit-2026-06-25.md`.
- ETC legacy batch compat route owner: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-route-owner-audit-2026-06-25.md`.
- Row318 implementation added `EtcLegacyBatchLifecycleService`, moved legacy OA draft/confirm/reopen lifecycle side effects out of `Application`, and kept HTTP body/header/detail/error mapping in `server.py`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-legacy-batch-read-payload-facade-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-draft-confirm-callback-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-delete-side-effect-service-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` legacy batch list/detail/payload helper sections
   - `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
   - `backend/src/fin_ops_platform/services/etc_legacy_batch_delete_service.py`
   - `backend/src/fin_ops_platform/services/etc_legacy_batch_lifecycle_service.py`
   - `docs/modules/etc-tickets/implementation-notes.md`
   - `tests/test_platform_runtime_boundary_guards.py`
   - targeted ETC legacy list/detail/query tests in `tests/test_etc_backend.py`
3. Use CodeGraph to inspect `_handle_api_etc_batches`, `_handle_api_etc_batch_detail`, `_etc_batch_list_items`, `_etc_batch_detail_payload`, `_etc_batch_counts` and related payload helpers.
4. Decide whether the next safe implementation is:
   - extracting a read payload facade/service;
   - moving list/detail HTTP ownership fully into `EtcLegacyBatchApiRoutes` with explicit read ports;
   - or writing a narrower analysis/static guard slice first.
5. Write an analysis file and update state machine with the selected next boundary.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not do broad `server.py` line-count splitting.
- Do not duplicate existing route owners, services or repositories.
- Do not change business/API response semantics without explicit tests.
- Do not pass the whole `Application` into route owners or services.
- Do not change business-batch v2 route behavior in this slice.
- Do not move read payload ownership until list/detail status/count semantics, business-batch unified view, attachment-status checks and targeted tests are explicitly accounted for.
