# Next Prompt

Continue after `server-py:etc-reconciliation-task-delete-side-effect-service-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-task-delete-side-effect-service-audit`.
- Commit-backed refresh: `.planning/refactors/modular-io-boundaries/analysis/commit-backed-state-reconciliation-2026-06-25-local-first-refresh.md`.
- Local closure reconciliation: `.planning/refactors/modular-io-boundaries/analysis/local-modular-code-closure-reconciliation-2026-06-25.md`.
- ETC route owner audit: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-residual-audit-2026-06-25.md`.
- ETC reconciliation task route owner implementation: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-route-owner-facade-extraction-2026-06-25.md`.
- ETC task delete side-effect audit: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-delete-side-effect-service-audit-2026-06-25.md`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-import-cleanup-service-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-delete-side-effect-service-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` cleanup helper sections
   - `backend/src/fin_ops_platform/services/etc_service.py`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_service.py`
   - `docs/modules/etc-tickets/implementation-notes.md`
   - `tests/test_platform_runtime_boundary_guards.py`
   - targeted ETC cleanup/delete tests in `tests/test_etc_backend.py`
3. Extract the shared import/submission/business-batch cleanup cluster into `EtcReconciliationImportCleanupService` with explicit dependencies/callbacks.
4. Keep HTTP body parsing, response shape and error mapping in `Application` for this first service slice.
5. Add service tests or static guard coverage as needed.
6. Run targeted ETC cleanup/delete API tests, platform boundary guards, docs verify and diff checks.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not do broad `server.py` line-count splitting.
- Do not duplicate existing route owners, services or repositories.
- Do not change business/API response semantics without explicit tests.
- Do not pass the whole `Application` into the new route owner.
- Do not change `/api/etc/import/*` or legacy `/api/etc/batches*` behavior in this slice.
- Do not move task delete side effects until relation preflight, rollback/idempotency, derived lifecycle refresh and tests are explicitly accounted for.
