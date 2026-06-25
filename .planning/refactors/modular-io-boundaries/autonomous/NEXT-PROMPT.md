# Next Prompt

Continue after `server-py:etc-reconciliation-task-payload-facade-extraction`.

## Current State

- Branch: `dev`.
- Last completed boundary: `server-py:etc-reconciliation-task-payload-facade-extraction`.
- Row334 status: `local-implementation-closed`.
- Analysis file: `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-payload-facade-extraction-2026-06-25.md`.
- `server.py` no longer defines `_handle_api_etc_reconciliation*` callbacks or the reconciliation task payload/read-shaping helper implementations.
- `EtcReconciliationTaskPayloadFacade` now owns task payload, unavailable payload, import blockers, imported invoice summary, source/parse issue shaping and `canConfirm`.
- Local modular implementation closure is not proven.
- Production browser/admin/write gates remain final validation gates, not the next local implementation step.

## Next Boundary

`server-py:etc-reconciliation-post-payload-facade-local-closure-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` and classify any dirty files.
2. Read:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-etc-reconciliation-task-payload-facade-extraction-2026-06-25.md`
   - `backend/src/fin_ops_platform/services/etc_reconciliation_task_payload_facade.py`
   - `backend/src/fin_ops_platform/app/routes_etc_reconciliation.py`
   - `backend/src/fin_ops_platform/app/server.py` route/factory residuals for ETC reconciliation
   - relevant payload and route-owner tests in `tests/test_etc_backend.py`
   - `tests/test_platform_runtime_boundary_guards.py`
3. Use CodeGraph before editing to inspect remaining `Application` callers/callees around `EtcReconciliationTaskApiRoutes`.
4. Audit only the post-payload-facade local closure boundary:
   - confirm no `_handle_api_etc_reconciliation*` callbacks remain;
   - confirm no task payload/read-shaping helper implementation remains in `Application`;
   - confirm route owner dependencies are explicit and no whole `Application` is passed;
   - identify any remaining residual route-specific `Application` ownership for this surface.
5. If no residual gap remains, mark the route-owner surface locally closed and select the next highest-risk local boundary outside this route surface.
6. Update analysis/state/docs and commit/push if verification passes.

## Stop Gates

- Do not change task payload response shape.
- Do not change import blockers, imported invoice summary or `canConfirm` semantics.
- Do not change runtime code unless the audit finds a narrow residual local implementation gap.
- Do not run production browser/admin/write validation.
- Do not perform production mutation.
