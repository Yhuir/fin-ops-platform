# Next Prompt

Continue after `production:read-model-production-evidence-matrix-read-only-sweep`.

## Current State

- Branch: `dev`
- Last completed boundary: `production:read-model-production-evidence-matrix-read-only-sweep`
- Last status: `production-controlled`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-workbench-matching-port-20260625020818`.
- Row245 collected a clean read-model production evidence matrix:
  - `/health/ready` returned `status=ready`, release-consistent, with required worker missing/stale/mismatch counts all `0`;
  - all `read_model.app_status_readiness` rows are `fresh`;
  - all `job.read_model_dirty_scopes` rows are `done`;
  - all read-model refresh outbox events are `done`;
  - read-model dead-letter groups are empty;
  - current read-model worker heartbeats are fresh;
  - read-model row-count and source-version tables are queryable;
  - Workbench high-row table counts are visible.
- Row245 also identified remaining gaps:
  - historical legacy `cost` and `tax` dirty-scope rows exist as `done` rows and need scope-contract dry-run classification;
  - browser/API/high-row smoke remains missing;
  - module-specific closure remains unproven.
- No global or module closure is claimed.

## Next Boundary

`production:read-model-scope-contract-runtime-dry-run-classification`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before selecting work.
3. Read:
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `docs/modules/read-models/README.md`
   - `scripts/check-read-model-scope-contracts.py`
   - `docs/operations/runtime-worker-governance.md` if runtime governance details are needed
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Write and execute a bounded read-only/dry-run classification plan for runtime read-model scope contracts.
5. Run the existing production read-model scope-contract checker in dry-run/read-only mode only.
6. Record invalid or legacy runtime scope rows, whether they are current-effective blockers, and an apply-or-defer decision.
7. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` with the result and next boundary.

## Stop Gates

- Do not run `--apply` in this classification slice.
- Do not mutate DB rows, readiness, dirty scopes, outbox events, queues or runtime services.
- Do not deploy, restart, requeue, repair, replay workers or print secrets.
- Stop if the checker requires guessing unknown scope contracts.
- Stop and classify precisely if current-effective blockers appear.
