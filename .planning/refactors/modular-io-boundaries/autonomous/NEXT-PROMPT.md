# Next Prompt

Continue the autonomous modular IO refactor after the `planning:post-workbench-compute-evidence-gate-next-boundary-selection` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:post-workbench-compute-evidence-gate-next-boundary-selection`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- Workbench compute production/runtime evidence was deferred; all Go admission rows remain `blocked-by-prerequisite`.
- The next selected non-Go shared-boundary slice is `server-py:residual-route-handler-boundary-audit`.

## Next Boundary

`server-py:residual-route-handler-boundary-audit`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, and this prompt.
5. Read target evidence:
   - `.planning/refactors/modular-io-boundaries/01-CURRENT-STATE-AUDIT.md`
   - `.planning/refactors/modular-io-boundaries/04-IMPLEMENTATION-ROADMAP.md`
   - `.planning/refactors/modular-io-boundaries/05-IMPACT-AND-TEST-GATES.md`
   - `.planning/refactors/modular-io-boundaries/analysis/planning-post-workbench-compute-evidence-gate-next-boundary-selection.md`
   - `docs/app-architecture/runtime-and-ownership.md`
   - `docs/modules/README.md`
   - `backend/src/fin_ops_platform/app/server.py`
   - existing `backend/src/fin_ops_platform/app/routes_*.py`
   - `tests/test_platform_runtime_boundary_guards.py`

## Boundary Scope

Target:

- Audit residual `server.py` route/handler/helper surfaces after prior route module work.
- Classify residual surfaces by:
  - likely module owner,
  - current caller evidence,
  - route/http mapping vs dependency assembly vs business logic,
  - read/write/read-model/worker side-effect risk,
  - legacy contamination risk,
  - deletion or extraction readiness.
- Identify exactly one next narrow implementation or follow-up audit boundary.
- Prefer a boundary that reduces old route/service contamination without changing business behavior.
- Do not move, delete or rewrite runtime code in this audit slice.
- Do not implement Go, Go Fiber or Go Worker.
- Do not perform production writes, deploy, restart services, requeue jobs, mark scopes done, mutate readiness, run repair tools with `--apply`, or execute production mutating HTTP scenarios.
- Do not change canonical Python runtime behavior in this audit slice.

Expected output:

- An analysis file under `.planning/refactors/modular-io-boundaries/analysis/` recording:
  - previous state,
  - current `server.py` residual inventory approach,
  - selected owner/risk categories,
  - next selected narrow boundary,
  - why no runtime code changed,
  - affected docs/tests,
  - seven-category test applicability,
  - state-machine impact.
- Updated `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, `NEXT-PROMPT.md`, and `prompts/04-master-goal-controller.md`.
- If test guard semantics change, update `tests/test_platform_runtime_boundary_guards.py`.
- `bash scripts/verify.sh docs`
- `git diff --check`

## Stop Condition

Complete one verified `server.py` residual handler audit slice: residual ownership/risk classification exists, exactly one next narrow boundary is pending, no runtime behavior changed, Go admission remains blocked, state-machine accounting is current, docs verification passes, the slice is committed and pushed to `origin/dev`, then continue to the selected next boundary unless a hard stop gate is hit.
