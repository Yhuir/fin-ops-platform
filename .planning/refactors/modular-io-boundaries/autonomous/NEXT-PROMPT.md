# Next Prompt

Continue after the `production:historical-dead-letter-covered-resolution-apply-runbook` slice.

## Current State

- Branch: `dev`
- Last completed boundary: `production:historical-dead-letter-covered-resolution-apply-runbook`
- Last status: `production-controlled`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-workbench-matching-port-20260625020818`.
- Workbench matching constructor fix remains deployed:
  - active release git commit is `b256db3a8fc370ce93e7b51bf62b1cd33176475d`;
  - `/health/ready` returned ready in the latest post-check.
- Historical read-model dead-letter residue was resolved through the controlled maintenance command:
  - pre-apply dry-run reported `candidate_count=24`, `eligible_count=24`, `resolved_count=0`;
  - apply command reported `mode=execute`, `candidate_count=24`, `eligible_count=24`, `resolved_count=24`;
  - post-check `job.outbox_events` had only `done=203169`;
  - dead-letter groups were `[]`;
  - `job.read_model_dirty_scopes` remained `done=187007`;
  - `read_model.app_status_readiness` remained `fresh=498`;
  - follow-up dry-run reported `candidate_count=0`, `eligible_count=0`, `resolved_count=0`.
- No requeue, republish, repair, worker replay, direct SQL, readiness mutation, dirty-scope mutation, deploy, restart or secret output occurred in the apply boundary.
- No global or module closure is claimed from residue cleanup alone.

## Next Boundary

`planning:post-historical-dead-letter-resolution-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before selecting work.
3. Read:
   - `analysis/production-historical-dead-letter-covered-resolution-apply-runbook-2026-06-25.md`
   - `analysis/production-historical-dead-letter-covered-resolution-read-only-maintenance-plan-2026-06-25.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Reconcile row 241 evidence and write a planning analysis for row 242.
5. Select the next highest-risk safe boundary from current queue facts, production evidence gaps and the commit-backed baseline.
6. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` with the selected next boundary.

## Stop Gates

- Do not repeat the covered-dead-letter apply command unless a new bounded runbook is written for a new residue set.
- Do not claim module/global closure from dead-letter cleanup alone.
- Do not requeue, republish, repair, run worker replay, mutate readiness or print secrets while selecting the next boundary.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
