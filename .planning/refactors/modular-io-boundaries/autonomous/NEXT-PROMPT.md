# Next Prompt

Continue after the `production:historical-dead-letter-covered-resolution-read-only-maintenance-plan` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `production:historical-dead-letter-covered-resolution-read-only-maintenance-plan`
- Last status: `analysis-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-workbench-matching-port-20260625020818`.
- No-OA FK production blocker was fixed and converged:
  - exact event `3bc506fd-5662-4902-a9b9-19b0d8fbe4a6` is `done`;
  - `no_oa_bank_batch:all` dirty scope is `done`;
  - readiness is `fresh`;
  - `/health/ready` had no active queue/dirty/failed/stale blockers in the latest post-convergence check.
- Historical obsolete `dead_lettered` rows remain; do not clean them without a separate bounded maintenance boundary.
- Workbench matching constructor fix was deployed:
  - active release git commit is `b256db3a8fc370ce93e7b51bf62b1cd33176475d`;
  - `fin-ops-worker@workbench-matching.service` stayed `active/running` with stable `MainPID=3380166` and `NRestarts=0`;
  - `/health` and `/health/ready` returned ready;
  - dirty scopes are all done, readiness rows are all fresh;
  - post-deploy workbench-matching logs have no constructor `TypeError`.
- Row240 classified all 24 historical read-model dead-letter rows:
  - dry-run `candidate_count=24`;
  - `eligible_count=24`;
  - `resolved_count=0`;
  - every candidate has fresh readiness, later done and `active_dirty_count=0` proof.
- No cleanup or DB/queue/readiness mutation has been executed yet.
- No global module closure is claimed.

## Next Boundary

`production:historical-dead-letter-covered-resolution-apply-runbook`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains the controller files from this handoff, and branch is `dev`.
2. Pull `origin/dev` with `--ff-only` when the working tree is clean; if local branch config reports multiple branches, use `git fetch origin` and verify `HEAD == origin/dev`.
3. Read:
   - `analysis/production-post-convergence-readiness-worker-db-aggregate-evidence-sweep-2026-06-25.md`
   - `analysis/production-no-oa-bank-batch-fk-fix-deploy-and-convergence-runbook-2026-06-25.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Read `analysis/production-historical-dead-letter-covered-resolution-read-only-maintenance-plan-2026-06-25.md`.
5. Write a bounded production apply runbook before any mutation.
6. Recheck `/health/ready`, no active dirty scopes, all readiness fresh, and `resolve-covered-dead-letters --dry-run`.
7. Execute `resolve-covered-dead-letters --execute` only if dry-run still reports all current candidates eligible.
8. Post-check dead-letter count, health/readiness/dirty scopes, and record whether historical dead-letter residue decreased without readiness regression.

## Stop Gates

- Do not requeue, republish, repair, run worker replay or mutate readiness.
- Do not execute cleanup unless the apply runbook pre-checks prove all current candidates eligible.
- No secret/env/DSN output.
- Stop if `/health/ready` regresses, active dirty scopes appear, readiness is non-fresh, or dry-run eligibility differs from the apply plan.
