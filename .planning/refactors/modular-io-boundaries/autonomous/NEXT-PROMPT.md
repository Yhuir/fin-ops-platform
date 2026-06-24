# Next Prompt

Continue after the `planning:parallel-orchestration-workflow` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:parallel-orchestration-workflow`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Parallel orchestration is now controller-led.
- Worker prompts may auto-progress inside assigned workstreams, but they do not own global state or global closure.
- Controller-only files are defined in `12-PARALLEL-ORCHESTRATION.md`.
- No module is globally closed because real PostgreSQL/worker/App Status/high-row/browser evidence remains deferred where unavailable.
- No Go/Fiber/Go Worker candidate has passed admission.
- `GET /api/workbench/groups/detail` freshness/source-version/read-model-status proof is already owned by `WorkbenchQueryFacade.group_detail(...)`.
- `Application._handle_api_workbench_group_detail(...)` still owns HTTP-level zone/group-id validation and response mapping.

## Next Boundary

`server-py:workbench-group-detail-route-owner-extraction`

## Options

Single-thread continuation:

- Use `prompts/04-master-goal-controller.md`.
- Start with `server-py:workbench-group-detail-route-owner-extraction`.

Parallel continuation:

- Read `12-PARALLEL-ORCHESTRATION.md`.
- Start T0 from `prompts/05-parallel-thread-prompts.md`.
- Start T1 for `server-py:workbench-group-detail-route-owner-extraction`.
- Start other workers only if their assigned file ownership does not overlap with T1 or controller-only files.

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Merge `origin/main` into `dev` only if conflict-free.
4. Reconcile `MODULE-QUEUE.md`, `STATE.md`, `JOURNAL.md`, this prompt, and `12-PARALLEL-ORCHESTRATION.md`.
5. If running parallel, enforce the direct-dev write lease before any worker edits files.

## Stop Condition

Proceed only through either the single-thread controller or the controller-led parallel workflow. Do not run several master controllers against `dev` without the controller/worker permissions and write lease from `12-PARALLEL-ORCHESTRATION.md`.
