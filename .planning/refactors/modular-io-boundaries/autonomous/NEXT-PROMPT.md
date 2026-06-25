# Next Prompt

Continue after `server-py:etc-legacy-batch-delete-side-effect-service-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-legacy-batch-delete-side-effect-service-audit`.
- Row317 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-delete-side-effect-service-audit-2026-06-25.md`.
- Local closure reconciliation: `.planning/refactors/modular-io-boundaries/analysis/local-modular-code-closure-reconciliation-2026-06-25.md`.
- ETC legacy batch compat route owner: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-route-owner-audit-2026-06-25.md`.
- Row317 implementation added `EtcLegacyBatchDeleteService`, moved non-business legacy batch DELETE side effects out of `Application`, and kept HTTP mapping/business-batch fallback in `server.py`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-legacy-batch-draft-confirm-callback-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-delete-side-effect-service-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-legacy-batch-route-owner-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` legacy batch draft/create/confirm/mark-not-submitted sections
   - `backend/src/fin_ops_platform/app/routes_etc_legacy_batches.py`
   - `backend/src/fin_ops_platform/services/etc_legacy_batch_delete_service.py`
   - `docs/modules/etc-tickets/implementation-notes.md`
   - `tests/test_platform_runtime_boundary_guards.py`
   - targeted ETC legacy draft/confirm/mark-not-submitted tests in `tests/test_etc_backend.py`
3. Use CodeGraph to inspect legacy batch draft/confirm callbacks, OA draft creation paths, manual submitted/not-submitted transitions, refresh/persist sequencing and task state transitions.
4. Decide whether the next safe implementation is:
   - moving draft/confirm HTTP ownership into `EtcLegacyBatchApiRoutes` with explicit ports;
   - extracting an operation-result service for draft/confirm side effects;
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
- Do not move draft/confirm side effects until OA client errors, task transitions, refresh/persist sequencing and tests are explicitly accounted for.
