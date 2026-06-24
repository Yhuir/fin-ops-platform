# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:workbench-withdraw-link-route-owner-extraction` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:workbench-withdraw-link-route-owner-extraction`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `LegacyWorkbenchActionRoutes` owns old `/workbench/actions/confirm|difference|exception|offline|offset`.
- `WorkbenchActionApiRoutes` now owns `/api/workbench/exception/preview`, `/api/workbench/exception/apply`, `/api/workbench/actions/confirm-link/preview`, `/api/workbench/actions/confirm-link`, `/api/workbench/actions/mark-exception`, `/api/workbench/actions/cancel-link`, and `/api/workbench/actions/withdraw-link` mapping/delegation boundaries.
- Cash special and the other remaining `/api/workbench/actions/*` wrappers still live in `server.py` and delegate to `WorkbenchWriteFacade`.

## Next Boundary

`server-py:workbench-cash-special-route-owner-extraction`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-withdraw-link-route-owner-extraction.md`
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-modern-workbench-action-route-owner-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench_actions.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_workbench_write_characterization.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Move cash special action facade delegation behind `WorkbenchActionApiRoutes` without changing behavior.
- Candidate endpoints are:
  - `/api/workbench/actions/confirm-cash-pass-through`
  - `/api/workbench/actions/confirm-cash-ticket-purchase`
  - `/api/workbench/actions/cancel-cash-special`
- Preserve current behavior exactly:
  - Invalid JSON remains handled by `Application._load_json_body(...)`.
  - Freshness guard remains in `Application` for this slice unless a reviewed helper preserves it exactly.
  - `request_id` forwarding remains unchanged.
  - Existing `WorkbenchWriteFacade.confirm_cash_pass_through(...)`,
    `confirm_cash_ticket_purchase(...)`, and `cancel_cash_special(...)` remain
    the delegates through the route owner.
  - Response shape, idempotency, stale expected-relation conflict, metadata
    mutation, affected scopes, operation projection and operation barrier
    behavior remain unchanged.
- If the three cash special endpoints are too broad for one safe slice, split
  row 202 into the first narrower cash special endpoint and update queue/state
  before implementation.
- Add or update static guards proving cash special facade delegation is no
  longer app-owned once extracted.

Do not:

- Do not move bank exception, OA-bank exception, personal advance repayment, cancel exception, ignore, unignore, exception preview/apply, confirm-link preview/submit, mark-exception, cancel-link or withdraw-link routes in this slice.
- Do not change response shapes, status codes, auth, freshness guard, timing headers, idempotency, relation semantics, operation barrier behavior, read model refresh behavior, frontend API behavior, or legacy `/workbench/actions/*` behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- `WorkbenchActionApiRoutes` method(s) that own cash special facade delegation while preserving app-level gates.
- Updated `server.py` delegation.
- Updated `tests/test_platform_runtime_boundary_guards.py` if guard semantics change.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated module implementation notes if behavior/ownership facts change.
- Targeted API/static verification, `bash scripts/verify.sh docs`, and `git diff --check`.

## Stop Condition

Complete one verified route-owner extraction slice for cash special actions or split row 202 into a narrower verified cash special boundary: behavior is preserved by tests, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
