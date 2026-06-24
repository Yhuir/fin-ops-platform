# Next Prompt

Continue after the `planning:post-production-baseline-module-closure-wave-selection` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:post-production-baseline-module-closure-wave-selection`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-workbench-matching-port-20260625020818`.
- Row243 collected a clean post-dead-letter production baseline:
  - `/health` and `/health/ready` ready and release-consistent;
  - required worker missing/stale/mismatch counts all `0`;
  - API, dispatcher and 20 worker units active/running with `NRestarts=0`;
  - `job.outbox_events` only `done=203169`;
  - no read-model dead-letter groups;
  - `job.read_model_dirty_scopes` only `done=187007`;
  - `read_model.app_status_readiness` only `fresh=498`;
  - covered-dead-letter dry-run returned zero candidates;
  - recent worker error grep returned no matching lines.
- Row244 selected the next boundary:
  - final closure is premature;
  - Go remains blocked;
  - worker waves are deferred until production DB/readiness/scope/source-version facts are matrixed;
  - next boundary is T0-only read-model production evidence matrix.
- No global or module closure is claimed.

## Next Boundary

`production:read-model-production-evidence-matrix-read-only-sweep`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before selecting work.
3. Read:
   - `analysis/planning-post-production-baseline-module-closure-wave-selection-2026-06-25.md`
   - `analysis/production-post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep-2026-06-25.md`
   - `analysis/commit-backed-state-reconciliation-2026-06-25.md`
   - `docs/modules/read-models/README.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Write and execute a bounded read-only production evidence matrix for registered read models.
5. Collect non-secret evidence:
   - readiness counts by read model, scope type and status;
   - dirty-scope counts by read model/scope and status;
   - outbox read-model event counts by event type/status and recent activity windows;
   - safe row-count/high-row signals where table ownership is known;
   - source-version/status samples where exposed by existing readiness/read-model tables or deployed-runtime helpers;
   - worker unit/heartbeat coverage mapped to read-model keys;
   - explicit remaining browser/API/high-row gaps.
6. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` with the result and next boundary.

## Stop Gates

- This is read-only evidence collection only.
- Do not claim module/global closure from matrix evidence alone.
- Do not deploy, restart, requeue, repair, replay workers, mutate DB/readiness/dirty scopes or print secrets.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
- Stop and classify precisely if evidence collection finds active dirty scopes, non-fresh readiness, dead-letter groups, required worker problems or unknown table contracts that would require guessing.
