# Next Prompt

Continue the autonomous modular IO refactor after the `server-py:workbench-legacy-action-handler-quarantine-audit` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `server-py:workbench-legacy-action-handler-quarantine-audit`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- The audit found the dangerous old chain is the legacy `/workbench/actions/*` route group, not the modern `/api/workbench/actions/*` facade path.
- Old `/workbench/actions/confirm|difference|exception|offline|offset` handlers directly call `ManualReconciliationService` and `LedgerService`.
- Modern `/api/workbench/actions/*` wrappers delegate to `WorkbenchWriteFacade`.
- The next selected non-Go shared-boundary slice is `server-py:legacy-workbench-action-route-module-quarantine`.

## Next Boundary

`server-py:legacy-workbench-action-route-module-quarantine`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/analysis/server-py-workbench-legacy-action-handler-quarantine-audit.md`
   - `docs/modules/reconciliation-workbench/README.md`
   - `docs/modules/reconciliation-workbench/tests.md`
   - `docs/modules/workbench-relations/README.md`
   - `docs/modules/workbench-relations/implementation-notes.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - `backend/src/fin_ops_platform/app/routes_workbench.py`
   - `backend/src/fin_ops_platform/services/reconciliation.py`
   - `backend/src/fin_ops_platform/services/ledger_service.py`
   - `backend/src/fin_ops_platform/services/workbench_write_facade.py`
   - `tests/test_app.py`
   - `tests/test_ledger_api.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Isolate old `/workbench/actions/confirm`, `/workbench/actions/difference`, `/workbench/actions/exception`, `/workbench/actions/offline`, and `/workbench/actions/offset` HTTP/payload mapping behind an explicit legacy Workbench action route owner.
- Preserve current legacy endpoint behavior and tests.
- Keep modern `/api/workbench/actions/*` behavior unchanged and facade-backed.
- Add or update static guard coverage proving:
  - legacy `/workbench/actions/*` is classified as compat-only,
  - modern `/api/workbench/actions/*` continues to delegate through `WorkbenchWriteFacade`,
  - legacy handlers do not become modern Workbench relation/read model endpoints,
  - Go/Fiber/Go Worker remains blocked.
- Update `docs/modules/workbench-relations/implementation-notes.md` or reconciliation Workbench docs if the compatibility boundary changes.

Do not:

- Do not remove legacy endpoint behavior in this slice unless tests prove it is unused and the deletion is narrower than quarantine.
- Do not migrate ledger/follow-up semantics into modern Workbench relation command service in this slice.
- Do not change API response shapes, status codes, ledger/reminder behavior, Workbench relation semantics, read model refresh behavior, permissions or frontend behavior.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.

Expected output:

- Runtime code isolates old legacy route mapping without changing behavior.
- Static guard documents and enforces the compat-only boundary.
- Tests updated only where needed for the new route owner.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- Updated implementation notes if the compat boundary changes.
- Targeted legacy route/API verification, docs verification and `git diff --check`.

## Suggested Verification

Run at least:

```bash
PYTHONPATH=backend/src python3 -m unittest tests.test_app.AppTests.test_health_endpoint_reports_current_and_future_capabilities tests.test_ledger_api -v
PYTHONPATH=backend/src python3 -m unittest tests.test_platform_runtime_boundary_guards.PlatformRuntimeBoundaryGuardTests.test_workbench_compute_go_shadow_admission_remains_guarded -v
bash scripts/verify.sh docs
git diff --check
```

Add narrower or broader Workbench tests if the implementation touches modern `/api/workbench/actions/*`.

## Stop Condition

Complete one verified legacy route quarantine implementation slice: old `/workbench/actions/*` mapping is isolated behind an explicit legacy owner or otherwise safely quarantined, modern `/api/workbench/actions/*` remains facade-backed, state-machine accounting is current, verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
