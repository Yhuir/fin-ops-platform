# Next Prompt

Continue after the `planning:commit-backed-state-reconciliation` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:commit-backed-state-reconciliation`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Parallel orchestration is now controller-led.
- Worker prompts may auto-progress inside assigned workstreams, but they do not own global state or global closure.
- Controller-only files are defined in `12-PARALLEL-ORCHESTRATION.md`.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- T0 accepted T1-T8 handoffs and integrated them in commit `b60a343a`.
- `GET /api/workbench/groups/detail` HTTP validation and facade response mapping now live in `WorkbenchGroupDetailApiRoutes`; freshness/source-version/read-model-status proof remains owned by `WorkbenchQueryFacade.group_detail(...)`.
- T6 collected partial production-read-only evidence, but `/health/ready` timed out and `fin-ops-worker@workbench.service` was `activating/auto-restart`; no production closure should be claimed from this evidence.
- T7 Go admission remains `go-candidate-deferred`.
- Commit-backed reconciliation report: `analysis/commit-backed-state-reconciliation-2026-06-25.md`.
- Queue evidence after reconciliation: 124 local proof/guard rows, 79 docs/analysis-only rows, 22 deferred rows and one remaining pending row.
- No product module has `Module Closure = closed`; production evidence closure and Go admission remain 0%.

## Next Boundary

`planning:post-parallel-handoff-next-boundary-selection`

## Options

Recommended autonomous continuation:

- Use `prompts/06-t0-meta-orchestrator-goal.md`.
- Start exactly one T0 `/goal` thread.
- T0 will execute `planning:post-parallel-handoff-next-boundary-selection`, using the commit-backed reconciliation report as the source of truth.
- After selecting the next safe boundary, T0 may create worker threads when safe, monitor them, accept/reject handoffs, update controller-only state files, commit/push to `origin/dev`, and continue the loop.
- Do not manually start old T1-T9 worker prompts unless T0 explicitly instructs that fallback.

Single-thread fallback:

- Use `prompts/04-master-goal-controller.md`.
- Start with `planning:post-parallel-handoff-next-boundary-selection`.

Manual parallel fallback:

- Read `12-PARALLEL-ORCHESTRATION.md`.
- `prompts/05-parallel-thread-prompts.md` is retained only as worker archetype/reference material.
- Manual T1-T9 startup is deprecated for unattended runs. Prefer T0-created worker threads from `06-t0-meta-orchestrator-goal.md`.
- If manual fallback is unavoidable, start T0 first to select the next worker boundary from accepted handoff risks. Do not start new workers from stale assumptions.

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Read `analysis/commit-backed-state-reconciliation-2026-06-25.md`, `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, this prompt, and `12-PARALLEL-ORCHESTRATION.md`.
5. If running parallel, enforce the direct-dev write lease before any worker edits files.
6. Use the completed commit-backed audit as the progress baseline; do not recalculate from memory or raw row counts alone.
7. Reconcile accepted handoff risks before assigning new workers: adjacent server route-owner work, production-readiness/runbook follow-up, read-model contract gaps, frontend combined freshness propagation and Go admission blockers.

## Stop Condition

Proceed only through either the single-thread controller or the controller-led parallel workflow. Do not run several master controllers against `dev` without the controller/worker permissions and write lease from `12-PARALLEL-ORCHESTRATION.md`.
