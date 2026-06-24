# Next Prompt

Continue after `planning:read-model-module-closure-evidence-ownership-map`.

## Current State

- Branch: `dev`
- Last completed boundary: `planning:read-model-module-closure-evidence-ownership-map`
- Last status: `planning-closed`
- Queue semantics remain corrected: slice status is not module closure.
- Latest deployed production release from prior evidence: `dev-workbench-matching-port-20260625020818`.
- Row245 production matrix is clean for current read-model runtime health:
  - all App Status read-model readiness rows are `fresh`;
  - all dirty scopes are `done`;
  - read-model outbox events are `done`;
  - no read-model dead-letter groups remain;
  - current workers have fresh heartbeats;
  - read-model row-count/source-version tables are queryable;
  - Workbench high-row table counts are visible.
- Row246 scope-contract classification is clean:
  - cost-statistics scope contract dry-run returned `ok=true`, `violation_count=0`, no covered historical failures and no current uncovered failures;
  - invalid read-model scope dry-run returned `ok=true`, `invalid_scope_count=0`;
  - legacy `cost`/`tax` rows are historical `done` dirty-scope rows only.
- Row248 wrote `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`:
  - mapped read-model-heavy modules to route/API surfaces;
  - attached local docs/test owners;
  - attached row245/246 production evidence;
  - listed remaining authenticated API, browser and high-row gaps;
  - classified evidence as worker local evidence, browser/API smoke, or T0 production read-only;
  - proposed four non-overlapping worker ownership scopes and handoff paths.
- Browser/API/high-row smoke and module-specific closure audits remain open.
- No global or module closure is claimed.
- No worker thread has been created for the new wave yet.

## Next Boundary

`planning:read-model-module-closure-worker-wave-1-prompts`

## Required First Steps On Resume

1. Confirm `git status --short --branch` is clean or only contains controller files from this handoff, and branch is `dev`.
2. Fetch `origin` and verify local `HEAD == origin/dev` before selecting work.
3. Read:
   - `analysis/read-model-module-closure-evidence-ownership-map-2026-06-25.md`
   - `analysis/planning-post-scope-contract-runtime-classification-next-boundary-selection-2026-06-25.md`
   - `analysis/production-read-model-production-evidence-matrix-read-only-sweep-2026-06-25.md`
   - `analysis/production-read-model-scope-contract-runtime-dry-run-classification-2026-06-25.md`
   - `analysis/commit-backed-state-reconciliation-2026-06-25.md`
   - `docs/modules/README.md`
   - `docs/modules/read-models/README.md`
   - `docs/modules/read-models/state-machine.md`
   - `docs/modules/read-models/tests.md`
   - `autonomous/MODULE-QUEUE.md`
   - `autonomous/STATE.md`
   - `autonomous/JOURNAL.md`
   - this prompt
   - `12-PARALLEL-ORCHESTRATION.md`
4. Generate a controller analysis file for the worker wave, for example:
   - `analysis/read-model-module-closure-worker-wave-1-prompts-2026-06-25.md`
5. Convert row248's four proposed scopes into concrete worker prompts:
   - Workbench / workbench-relations / turnover-ledger.
   - Input invoice usage / output invoice collections / OA pending payments / invoice lifecycle.
   - Bank details / bank account balance / pending invoices / no-OA bank batches / search.
   - Cost statistics / tax offset.
6. For each worker prompt, include:
   - base commit;
   - exact goal;
   - assigned owned files;
   - forbidden controller files;
   - required docs and analysis files to read;
   - architecture gates;
   - required local evidence/test mapping;
   - exact handoff path;
   - stop condition;
   - no production mutation;
   - no module/global closure claim;
   - Simplified Chinese final answer requirement.
7. Use thread tools only after prompts and ownership are written and reviewed in the analysis file.
8. Track worker thread ids, assigned scope, file ownership, base commit, handoff path and status in the controller analysis file.
9. Update `STATE.md`, `MODULE-QUEUE.md`, `JOURNAL.md`, `NEXT-PROMPT.md` and `04-master-goal-controller.md` after prompt generation/thread creation.

## Stop Gates

- Do not claim module/global closure from row245, row246 or row248 evidence alone.
- Do not start a worker without exact owned files, forbidden files and handoff path.
- Do not let workers edit controller-only files.
- Do not run production `--apply`, deploy, restart, requeue, repair, replay workers or mutate runtime state in this planning slice.
- Stop if current `dev` diverges from `origin/dev` or the worktree contains unrelated dirty files.
