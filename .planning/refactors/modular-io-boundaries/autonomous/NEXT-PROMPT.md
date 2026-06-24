# Next Prompt

Continue after `planning:post-scope-contract-runtime-classification-next-boundary-selection`.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:post-scope-contract-runtime-classification-next-boundary-selection`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release: `dev-workbench-matching-port-20260625020818`.
- Row245 production matrix is clean for current read-model runtime health:
  - all App Status read-model readiness rows are `fresh`;
  - all dirty scopes are `done`;
  - read-model outbox events are `done`;
  - no read-model dead-letter groups remain;
  - current workers have fresh heartbeats;
  - read-model row-count/source-version tables are queryable.
- Row246 scope-contract classification is clean:
  - cost-statistics scope contract dry-run returned `ok=true`, `violation_count=0`, no covered historical failures and no current uncovered failures;
  - invalid read-model scope dry-run returned `ok=true`, `invalid_scope_count=0`;
  - legacy `cost`/`tax` rows are historical `done` dirty-scope rows only.
- Row247 rejected final closure, production cleanup, immediate worker creation and Go admission as premature.
- Browser/API/high-row smoke and module-specific closure audits remain open.
- No global or module closure is claimed.

## Next Boundary

`planning:read-model-module-closure-evidence-ownership-map`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before selecting work.
3. Read:
   - `analysis/planning-post-scope-contract-runtime-classification-next-boundary-selection-2026-06-25.md`
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
   - `analysis/commit-backed-state-reconciliation-2026-06-25.md`
   - `docs/modules/README.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `MODULE-QUEUE.md`
   - `STATE.md`
   - `JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Build a controller-owned evidence and file-ownership map for read-model-heavy modules:
   - module key and route/API surface;
   - local implementation evidence files and test owners;
   - row245/246 production evidence applicable to the module;
   - remaining authenticated API, browser and high-row evidence gaps;
   - whether evidence is T0 production read-only, local test, browser smoke, or worker-thread suitable;
   - exact file ownership and handoff paths for any proposed worker wave.
5. Select exactly one next execution boundary after the map:
   - a bounded worker wave with ownership if safe;
   - a T0-only production read-only/API/browser smoke planning slice;
   - or a single targeted module closure audit.
6. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` with the map result and next boundary.

## Stop Gates

- Do not claim module/global closure from row245 or row246 evidence alone.
- Do not create worker threads until the ownership map is written.
- Do not run production `--apply`, deploy, restart, requeue, repair, replay workers or mutate runtime state in this planning slice.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
