# Next Prompt

Continue after `server-py:etc-reconciliation-route-owner-residual-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-route-owner-residual-audit`.
- Commit-backed refresh: `.planning/refactors/modular-io-boundaries/analysis/commit-backed-state-reconciliation-2026-06-25-local-first-refresh.md`.
- Local closure reconciliation: `.planning/refactors/modular-io-boundaries/analysis/local-modular-code-closure-reconciliation-2026-06-25.md`.
- ETC route owner audit: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-residual-audit-2026-06-25.md`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-task-route-owner-facade-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-residual-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc.py`
   - `backend/src/fin_ops_platform/app/server.py` ETC reconciliation task handler section
   - `tests/test_etc_backend.py` ETC reconciliation route tests
   - `tests/test_platform_runtime_boundary_guards.py`
3. Implement `EtcReconciliationTaskApiRoutes` as an explicit route owner for `/api/etc/reconciliation-tasks*`.
4. Keep heavy deletion/import side effects delegated through explicit callbacks if they are not ready for service extraction.
5. Update `server.py` to delegate reconciliation task routing to the new route owner.
6. Add or update static guard coverage proving delegation and preventing broad app-owned reconciliation task route handlers from returning.
7. Run targeted ETC backend tests, platform boundary guard tests, docs verify, and diff checks.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not do broad `server.py` line-count splitting.
- Do not duplicate existing route owners, services or repositories.
- Do not change business/API response semantics without explicit tests.
- Do not pass the whole `Application` into the new route owner.
- Do not change `/api/etc/import/*` or legacy `/api/etc/batches*` behavior in this slice.
