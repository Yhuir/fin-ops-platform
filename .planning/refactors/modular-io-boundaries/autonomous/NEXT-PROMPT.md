# Next Prompt

Continue after the `planning:parallel-handoff-review-and-state-update` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:parallel-handoff-review-and-state-update`
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

## Next Boundary

`planning:post-parallel-handoff-next-boundary-selection`

## Options

Single-thread continuation:

- Use `prompts/04-master-goal-controller.md`.
- Start with `planning:post-parallel-handoff-next-boundary-selection`.

Parallel continuation:

- Read `12-PARALLEL-ORCHESTRATION.md`.
- Start T0 from `prompts/05-parallel-thread-prompts.md`.
- Start T0 controller first to select the next worker boundary from accepted handoff risks.
- Do not start new workers from stale assumptions; generate prompts after T0 selects the next safe boundary.

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, this prompt, and `12-PARALLEL-ORCHESTRATION.md`.
5. If running parallel, enforce the direct-dev write lease before any worker edits files.
6. Reconcile accepted handoff risks before assigning new workers: adjacent server route-owner work, production-readiness/runbook follow-up, read-model contract gaps, frontend combined freshness propagation and Go admission blockers.

## Stop Condition

Proceed only through either the single-thread controller or the controller-led parallel workflow. Do not run several master controllers against `dev` without the controller/worker permissions and write lease from `12-PARALLEL-ORCHESTRATION.md`.
