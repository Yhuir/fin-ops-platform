# Next Prompt

Continue after `server-py:etc-import-route-owner-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-import-route-owner-audit`.
- Commit-backed refresh: `.planning/refactors/modular-io-boundaries/analysis/commit-backed-state-reconciliation-2026-06-25-local-first-refresh.md`.
- Local closure reconciliation: `.planning/refactors/modular-io-boundaries/analysis/local-modular-code-closure-reconciliation-2026-06-25.md`.
- ETC route owner audit: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-residual-audit-2026-06-25.md`.
- ETC reconciliation task route owner implementation: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-route-owner-facade-extraction-2026-06-25.md`.
- ETC task delete side-effect audit: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-delete-side-effect-service-audit-2026-06-25.md`.
- ETC import cleanup service extraction: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-import-cleanup-service-extraction-2026-06-25.md`.
- ETC reconciliation delete callback route owner: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-delete-route-callback-audit-2026-06-25.md`.
- ETC import route owner: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-import-route-owner-audit-2026-06-25.md`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-legacy-batch-route-owner-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-import-route-owner-audit-2026-06-25.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-residual-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` legacy `/api/etc/batches*` sections
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/app/routes_etc_import.py`
   - `docs/modules/etc-tickets/implementation-notes.md`
   - `tests/test_platform_runtime_boundary_guards.py`
   - targeted ETC legacy batch/list/delete/draft tests in `tests/test_etc_backend.py`
3. Use CodeGraph to inspect legacy `/api/etc/batches*` handlers, existing `EtcBusinessBatchApiRoutes`, delete/reset/revoke side effects and compatibility payload helpers.
4. Decide whether the next safe implementation is extracting a compat-only legacy batch route owner, delegating more paths to `EtcBusinessBatchApiRoutes`, extracting a side-effect service first, or marking a compat path for quarantine/removal with guard.
5. Write an analysis file and update state machine with the selected next boundary.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not do broad `server.py` line-count splitting.
- Do not duplicate existing route owners, services or repositories.
- Do not change business/API response semantics without explicit tests.
- Do not pass the whole `Application` into the new route owner.
- Do not change business-batch v2 route behavior in this slice.
- Do not move legacy batch delete/reset/revoke side effects until relation cleanup, task cleanup, rollback/idempotency, derived lifecycle refresh and tests are explicitly accounted for.
