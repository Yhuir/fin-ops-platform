# Next Prompt

Continue after `server-py:etc-reconciliation-route-owner-local-closure-audit`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-route-owner-local-closure-audit`.
- Row332 status: `analysis-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-local-closure-audit-2026-06-25.md`.
- `server.py` no longer defines `_handle_api_etc_reconciliation*` callbacks.
- ETC reconciliation route-owner local closure is not proven because task payload/read-shaping helpers still live in `Application`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-task-payload-facade-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-route-owner-local-closure-audit-2026-06-25.md`
   - `backend/src/fin_ops_platform/app/server.py` payload helpers:
     - `_etc_reconciliation_task_payload(...)`
     - `_etc_reconciliation_unavailable_task_payload(...)`
     - `_etc_reconciliation_import_blockers(...)`
     - `_etc_reconciliation_imported_invoice_summary(...)`
     - `_etc_reconciliation_task_can_confirm(...)`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - relevant payload tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect payload helper callers/callees.
4. Audit only the payload facade boundary:
   - classify payload helpers as route facade, service, or reusable serializer ownership;
   - identify tests that freeze response shape;
   - select the next smallest implementation boundary.
5. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change task payload response shape.
- Do not change import blockers, imported invoice summary or `canConfirm` semantics.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
