# Next Prompt

Continue after `server-py:etc-reconciliation-task-route-owner-facade-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-task-route-owner-facade-extraction`.
- Commit-backed refresh: `.planning/refactors/modular-io-boundaries/analysis/commit-backed-state-reconciliation-2026-06-25-local-first-refresh.md`.
- Local closure reconciliation: `.planning/refactors/modular-io-boundaries/analysis/local-modular-code-closure-reconciliation-2026-06-25.md`.
- ETC route owner audit: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-residual-audit-2026-06-25.md`.
- ETC reconciliation task route owner implementation: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-route-owner-facade-extraction-2026-06-25.md`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-task-delete-side-effect-service-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-route-owner-facade-extraction-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` task delete/imported-invoice delete callback sections
   - `docs/modules/etc-tickets/implementation-notes.md`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph to inspect `_handle_api_etc_reconciliation_task_delete`, `_handle_api_etc_reconciliation_imported_invoices_delete`, `_remove_reconciliation_task_imported_invoices`, `_delete_reconciliation_task_*`, `_cancel_etc_summary_relations_for_batch*`, and callers.
4. Classify whether the next safe slice is a service extraction, explicit side-effect port extraction, or compat-only quarantine.
5. Write an analysis file and update state machine with the selected next implementation boundary.

## Stop Gates

- Do not run production browser/admin/write validation.
- Do not perform production mutation.
- Do not do broad `server.py` line-count splitting.
- Do not duplicate existing route owners, services or repositories.
- Do not change business/API response semantics without explicit tests.
- Do not pass the whole `Application` into the new route owner.
- Do not change `/api/etc/import/*` or legacy `/api/etc/batches*` behavior in this slice.
- Do not move task delete side effects until relation preflight, rollback/idempotency, derived lifecycle refresh and tests are explicitly accounted for.
