# Next Prompt

Continue after the `runtime-workers:workbench-matching-orchestrator-constructor-fix` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `runtime-workers:workbench-matching-orchestrator-constructor-fix`
- Last status: `implementation-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-no-oa-fk-20260625014906`.
- No-OA FK production blocker was fixed and converged:
  - exact event `3bc506fd-5662-4902-a9b9-19b0d8fbe4a6` is `done`;
  - `no_oa_bank_batch:all` dirty scope is `done`;
  - readiness is `fresh`;
  - `/health/ready` had no active queue/dirty/failed/stale blockers in the latest post-convergence check.
- Historical obsolete `dead_lettered` rows remain; do not clean them without a separate bounded maintenance boundary.
- The post-convergence production aggregate was clean for active dirty scopes and App Status readiness, but `fin-ops-worker@workbench-matching.service` was in a systemd restart loop.
- The local fix is implemented: `WorkbenchMatchingWorkerFactory` now passes `relation_read_port=WorkbenchMatchingRelationReadPort(pair_relation_service)` to `WorkbenchMatchingOrchestrator`.
- Local verification passed for py_compile, targeted runtime boundary guard, Workbench matching orchestrator tests, docs verify and diff check.
- No global module closure is claimed.

## Next Boundary

`production:workbench-matching-constructor-fix-deploy-and-convergence-runbook`

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
4. Confirm row237 is committed and pushed to `origin/dev`.
5. Write a bounded production deploy/convergence runbook before any production mutation.
6. Deploy the fix with the repository deploy script from clean `dev`.
7. Post-check:
   - active release identity;
   - `fin-ops-worker@workbench-matching.service` active/running and stable restart count;
   - `/health` and `/health/ready`;
   - active dirty scopes, readiness aggregates and worker problem samples;
   - workbench-matching logs have no new constructor TypeError.

## Stop Gates

- Do not requeue, resolve, repair, run worker replay or mutate readiness unless a separate explicit stop-gate analysis proves it is bounded and necessary.
- No secret/env/DSN output.
- Stop if deploy script fails, readiness regresses, worker restart count continues rising after the deployed fix, or logs show a new non-constructor blocker requiring diagnosis.
