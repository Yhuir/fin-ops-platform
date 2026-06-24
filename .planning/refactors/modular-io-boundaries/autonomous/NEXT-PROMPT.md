# Next Prompt

Continue after the `production:post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `production:post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep`
- Last status: `production-controlled`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-workbench-matching-port-20260625020818`.
- Row243 collected a clean post-dead-letter production baseline:
  - `/health` and `/health/ready` ready and release-consistent;
  - required worker missing/stale/mismatch counts all `0`;
  - API, dispatcher and 20 `fin-ops-worker@*.service` units active/running with `NRestarts=0` across a stability recheck;
  - `job.outbox_events` only `done=203169`;
  - no read-model dead-letter groups;
  - `job.read_model_dirty_scopes` only `done=187007`;
  - `read_model.app_status_readiness` only `fresh=498`;
  - covered-dead-letter dry-run returned zero candidates;
  - recent worker error grep returned no matching lines.
- No deploy, restart, requeue, repair, worker replay, DB/readiness/dirty-scope mutation or secret output occurred in row243.
- No global or module closure is claimed.

## Next Boundary

`planning:post-production-baseline-module-closure-wave-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before selecting work.
3. Read:
   - `analysis/production-post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep-2026-06-25.md`
   - `analysis/planning-post-historical-dead-letter-resolution-next-boundary-selection-2026-06-25.md`
   - `analysis/commit-backed-state-reconciliation-2026-06-25.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Reconcile which `production-evidence-deferred` / `not-module-closed` rows can be revisited using the clean production baseline.
5. Select the next highest-risk safe module-specific closure/evidence wave.
6. Decide whether the next wave is:
   - T0-only production evidence collection;
   - a bounded worker wave for independent module audits;
   - or a planning/accounting reconciliation before workers.
7. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` with the selected next boundary.

## Stop Gates

- Do not claim module/global closure from the clean global baseline alone.
- Do not start Go/Fiber/Go Worker implementation; Go admission remains blocked.
- Do not create workers unless ownership scopes are independent and current queue/state evidence is reconciled.
- Do not perform production mutation in this planning boundary.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
