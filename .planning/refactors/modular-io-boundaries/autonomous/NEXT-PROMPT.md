# Next Prompt

Continue after the `production:workbench-matching-constructor-fix-deploy-and-convergence-runbook` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `production:workbench-matching-constructor-fix-deploy-and-convergence-runbook`
- Last status: `production-controlled`
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
- No global module closure is claimed.

## Next Boundary

`planning:post-workbench-matching-production-convergence-next-boundary-selection`

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
4. Read `analysis/runtime-workers-workbench-matching-orchestrator-constructor-fix-2026-06-25.md`.
5. Read `analysis/production-workbench-matching-constructor-fix-deploy-and-convergence-runbook-2026-06-25.md`.
6. Reconcile the latest production-controlled evidence and select the next safe boundary.
7. Do not claim module/global closure from `/health/ready` and aggregate freshness alone; closure still needs commit-backed module criteria and remaining deferred evidence reviewed.

## Stop Gates

- Do not clean historical `dead_lettered` rows without a separate bounded maintenance boundary.
- Do not requeue, resolve, repair, run worker replay or mutate readiness inside this planning selection boundary.
- No secret/env/DSN output.
- Stop if the evidence contradicts queue/state files and cannot be reconciled from committed facts.
