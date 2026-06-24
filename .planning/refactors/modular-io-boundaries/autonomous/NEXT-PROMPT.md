# Next Prompt

Continue after the `planning:post-no-oa-production-convergence-next-boundary-selection` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:post-no-oa-production-convergence-next-boundary-selection`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-no-oa-fk-20260625014906`.
- No-OA FK production blocker was fixed and converged:
  - exact event `3bc506fd-5662-4902-a9b9-19b0d8fbe4a6` is `done`;
  - `no_oa_bank_batch:all` dirty scope is `done`;
  - readiness is `fresh`;
  - `/health/ready` had no active queue/dirty/failed/stale blockers in the latest post-convergence check.
- Historical obsolete `dead_lettered` rows remain; do not clean them without a separate bounded maintenance boundary.
- No global module closure is claimed.

## Next Boundary

`production:post-convergence-readiness-worker-db-aggregate-evidence-sweep`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Read:
   - `analysis/planning-post-no-oa-production-convergence-next-boundary-selection-2026-06-25.md`
   - `analysis/production-no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook-2026-06-25.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Write a read-only production evidence file before SSH collection.
5. Collect non-secret read-only aggregate evidence only:
   - release identity;
   - API/dispatcher/required worker status;
   - `/health` and `/health/ready`;
   - `job.outbox_events` status aggregates;
   - `job.read_model_dirty_scopes` status aggregates;
   - `read_model.app_status_readiness` aggregates;
   - no-OA exact scope;
   - historical dead-letter classification.

## Stop Gates

- No DB writes.
- No requeue, resolve, repair, deploy, restart, worker replay or readiness mutation.
- No secret/env/DSN output.
- If aggregate evidence shows new active blockers, select the narrowest diagnosis boundary rather than broad cleanup.
