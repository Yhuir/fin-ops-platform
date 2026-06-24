# Next Prompt

Continue after `production:read-model-scope-contract-runtime-dry-run-classification`.

## Current State

- Branch: `dev`
- Last completed boundary: `production:read-model-scope-contract-runtime-dry-run-classification`
- Last status: `production-controlled`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-workbench-matching-port-20260625020818`.
- Row245 collected a clean read-model production evidence matrix:
  - all App Status read-model readiness rows are `fresh`;
  - all dirty scopes are `done`;
  - read-model outbox events are `done`;
  - read-model dead-letter groups are empty;
  - current read-model workers have fresh heartbeats;
  - read-model row-count/source-version tables are queryable;
  - Workbench high-row table counts are visible.
- Row246 classified runtime scope-contract state in dry-run mode only:
  - `/health/ready` is ready on active API port `18001`;
  - cost-statistics scope contract dry-run returned `ok=true`, `violation_count=0`, `covered_historical_outbox_failure_count=0`, `current_uncovered_outbox_failure_count=0`;
  - invalid read-model scope dry-run returned `ok=true`, `invalid_scope_count=0`;
  - legacy `cost`/`tax` rows are historical `done` dirty-scope rows only, with no non-done samples, no active outbox rows and no readiness rows.
- No `--apply`, production mutation, requeue, repair, replay, restart or secret output occurred.
- Browser/API/high-row smoke and module-specific closure audits remain open.
- No global or module closure is claimed.

## Next Boundary

`planning:post-scope-contract-runtime-classification-next-boundary-selection`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before selecting work.
3. Read:
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
   - `analysis/commit-backed-state-reconciliation-2026-06-25.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Reconcile row245 and row246 evidence against remaining closure gaps.
5. Select exactly one next safe boundary. Likely candidates:
   - module-specific production closure audit wave selection;
   - bounded browser/API/high-row smoke planning;
   - targeted module closure audit for the highest-risk read model.
6. Do not create workers until file ownership and expected evidence are mapped.
7. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` with the result and next boundary.

## Stop Gates

- Do not claim module/global closure from row245 or row246 evidence alone.
- Do not run production `--apply`, deploy, restart, requeue, repair, replay workers or mutate runtime state in this planning slice.
- Do not create worker threads until a bounded ownership map exists.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
