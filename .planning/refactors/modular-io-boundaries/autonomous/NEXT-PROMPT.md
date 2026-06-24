# Next Prompt

Continue after the `planning:post-historical-dead-letter-resolution-next-boundary-selection` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:post-historical-dead-letter-resolution-next-boundary-selection`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-workbench-matching-port-20260625020818`.
- Row241 resolved the historical read-model dead-letter residue through a controlled maintenance command:
  - pre-apply dry-run reported `candidate_count=24`, `eligible_count=24`, `resolved_count=0`;
  - apply command reported `mode=execute`, `candidate_count=24`, `eligible_count=24`, `resolved_count=24`;
  - post-check `job.outbox_events` had only `done=203169`;
  - dead-letter groups were `[]`;
  - `job.read_model_dirty_scopes` remained `done=187007`;
  - `read_model.app_status_readiness` remained `fresh=498`;
  - follow-up dry-run reported `candidate_count=0`, `eligible_count=0`, `resolved_count=0`.
- Row242 selected the next evidence boundary:
  - dead-letter cleanup does not prove module/global closure;
  - the old commit-backed reconciliation baseline predates the latest production-control sequence;
  - the next safe boundary is a post-cleanup global production readiness/worker/DB evidence sweep.
- No global or module closure is claimed.

## Next Boundary

`production:post-dead-letter-resolution-global-readiness-worker-db-evidence-sweep`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before selecting work.
3. Read:
   - `analysis/planning-post-historical-dead-letter-resolution-next-boundary-selection-2026-06-25.md`
   - `analysis/production-historical-dead-letter-covered-resolution-apply-runbook-2026-06-25.md`
   - `analysis/production-workbench-matching-constructor-fix-deploy-and-convergence-runbook-2026-06-25.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Write and execute a bounded read-only evidence sweep for row243.
5. Collect non-secret production evidence:
   - `/health` and `/health/ready` release identity and readiness summary;
   - API, dispatcher and required worker unit status/stability samples;
   - deployed-runtime PostgreSQL aggregates for `job.outbox_events`, `job.read_model_dirty_scopes`, `read_model.app_status_readiness`;
   - worker heartbeat/status samples exposed by `/health/ready`;
   - recent required-worker error grep if useful.
6. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` with the result and next boundary.

## Stop Gates

- This is read-only evidence collection only.
- Do not deploy, restart, requeue, republish, repair, run worker replay, mutate DB, mutate dirty scopes, mutate readiness or print secrets.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
- Stop and classify precisely if `/health/ready` regresses, active dirty scopes appear, readiness is non-fresh, dead-letter groups return, or required workers are missing/stale/mismatched.
